import os
import re
import json
import uuid
import boto3
import traceback

from utils.response_utils import process_response
from common_logic.common_utils.logger_utils import get_logger
from common_logic.common_utils.websocket_utils import load_ws_client
from common_logic.common_utils.lambda_invoke_utils import (
    chatbot_lambda_call_wrapper,
    is_running_local,
)
from utils import executor
from utils.bot_util import get_bot_info_from_table, scan_bot_info_from_table

logger = get_logger("main")

session_table_name = os.environ.get("SESSION_TABLE_NAME", "")
message_table_name = os.environ.get("MESSAGE_TABLE_NAME", "")

websocket_url = os.environ.get("WEBSOCKET_URL", "")
openai_key_arn = os.environ.get("OPENAI_KEY_ARN", "")
region_name = os.environ.get("AWS_REGION", "us-west-2")

bot_table_name = os.environ.get("BOT_TABLE_NAME", "")
dynamodb_resource = boto3.resource("dynamodb")
bot_table = dynamodb_resource.Table(bot_table_name)

@chatbot_lambda_call_wrapper
def lambda_handler(event_body: dict, context: dict):
    logger.info(json.dumps(event_body, indent=2))
    if "query" in event_body and "ws_connection_id" in context:
        return web_socket_event_handler(event_body, context)
    else:
        return rest_api_event_handler(event_body, context)
        

def rest_api_event_handler(event_body: dict, context: dict):

    agent_flow_body = create_rest_api_agent_flow_body(event_body, context)
    
    try:
        response: dict = executor.run(agent_flow_body)
        r = process_response(agent_flow_body, response)
        
    except Exception as e:
        msg = traceback.format_exc()
        logger.exception("Main exception:%s" % msg)
        return "An exception has occurred"

    response_body = create_rest_api_llm_response_body(r.get("message"), response)

    return response_body

def web_socket_event_handler(event_body: dict, context: dict):

    stream = context['stream']

    agent_flow_body = create_ws_agent_flow_body(event_body, context)

    # debuging
    # show debug info directly in local mode
    if is_running_local():
        response: dict = executor.run(agent_flow_body)
        r = process_response(agent_flow_body, response)
        if not stream:
            return r
        return "All records have been processed"
    else:
        try:
            response: dict = executor.run(agent_flow_body)
            r = process_response(agent_flow_body, response)
            if not stream:
                return r
            return "All records have been processed"
        except Exception as e:
            msg = traceback.format_exc()
            logger.exception("Main exception:%s" % msg)
            return "An exception has occurred"

def create_rest_api_agent_flow_body(event_body: dict, context: dict):
    request_timestamp = context['request_timestamp']
    last_message = event_body.get("messages", [])[-1]
    user_profile = event_body.get("user_profile")
    bot_id = user_profile.get("channel")
    agent = user_profile.get("agent")
    if agent == 1:
        profile = "agent"
    else:
        profile = "host"
    
    query = last_message.get("content")
    session_id=event_body.get("session_id", None)
    context_round=event_body.get("context_round", 0)
    
    # fix user_id for now
    user_id = "default_user_id"
    chat_history = []
    if not session_id:
        session_id = f"{user_id}{request_timestamp}"

    agent_flow_body = {}
    agent_flow_body["query"] = query
    agent_flow_body["entry_type"] = "common"
    agent_flow_body["user_profile"] = profile
    agent_flow_body["bot_id"] = bot_id
    agent_flow_body["use_history"] = True
    agent_flow_body["enable_trace"] = False
    agent_flow_body["session_id"] = session_id
    agent_flow_body["chatbot_config"] = get_bot_info_from_table(bot_id)
    agent_flow_body["chat_history"] = chat_history
    agent_flow_body['request_timestamp'] = request_timestamp
    agent_flow_body['user_id'] = user_id
    agent_flow_body['message_id'] = str(uuid.uuid4())
    agent_flow_body['agent'] = agent
    agent_flow_body['context_round'] = context_round
    agent_flow_body['ddb_history_obj'] = []  # not used
    agent_flow_body['stream'] = False
    agent_flow_body['custom_message_id'] = ""
    agent_flow_body["ws_connection_id"] = ""

    return agent_flow_body

def create_ws_agent_flow_body(event_body: dict, context: dict):
    stream = context['stream']
    request_timestamp = context['request_timestamp']
    ws_connection_id = context.get('ws_connection_id')
    if stream:
        load_ws_client(websocket_url)

    client_type = event_body.get("client_type", "default_client_type")
    session_id = event_body.get("session_id", None)
    custom_message_id = event_body.get("custom_message_id", "")
    user_id = event_body.get("user_id", "default_user_id")

    if not session_id:
        session_id = f"session_{int(request_timestamp)}"

    # ddb_history_obj = DynamoDBChatMessageHistory(
    #     sessions_table_name=session_table_name,
    #     messages_table_name=message_table_name,
    #     session_id=session_id,
    #     user_id=user_id,
    #     client_type=client_type,
    # )
    #
    # chat_history = ddb_history_obj.messages_as_langchain
    chat_history = []

    # bot id must exist in request body
    bot_id = event_body.get("bot_id", "")
    event_body["chatbot_config"] = scan_bot_info_from_table(bot_id)
    event_body['stream'] = stream
    event_body["chat_history"] = chat_history
    event_body["ws_connection_id"] = ws_connection_id
    event_body['custom_message_id'] = custom_message_id
    event_body['ddb_history_obj'] = []  # not used
    event_body['request_timestamp'] = request_timestamp
    # event_body['chatbot_config']['user_id'] = user_id
    # event_body['chatbot_config']['group_name'] = group_name
    event_body['user_id'] = user_id
    event_body['message_id'] = str(uuid.uuid4())

    return event_body

def create_rest_api_llm_response_body(resp_message: dict, response: dict):
    response_body = {}
    response_body["role"] = resp_message.get("role")
    match_answer = re.search(r'<answer>([\s\S]*?)</answer>', resp_message.get("content"))
    if match_answer:
        content = match_answer.group(1)
        response_body["content"] = content
    else:
        response_body["content"] = resp_message.get("content")
    match_category = re.search(r'<category>(.*?)</category>', resp_message.get("content"))
    if match_category:
        category = match_category.group(1)
        response_body["category"] = category
    else:
        response_body["category"] = response.get("current_agent_intent_type")
    response_body["intent_id"] = "i0"
    response_body["intent_completed"] = "true"

    return response_body