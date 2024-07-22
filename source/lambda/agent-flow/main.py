import os
import json
import uuid
import boto3
import traceback

from common_logic.common_utils.ddb_utils import DynamoDBChatMessageHistory
from utils.response_utils import process_response
from common_logic.common_utils.logger_utils import get_logger
from common_logic.common_utils.websocket_utils import load_ws_client
from common_logic.common_utils.lambda_invoke_utils import (
    chatbot_lambda_call_wrapper,
    is_running_local,
)
from utils import executor

logger = get_logger("main")

session_table_name = os.environ.get("SESSION_TABLE_NAME", "")
message_table_name = os.environ.get("MESSAGE_TABLE_NAME", "")

websocket_url = os.environ.get("WEBSOCKET_URL", "")
openai_key_arn = os.environ.get("OPENAI_KEY_ARN", "")
region_name = os.environ.get("AWS_REGION", "us-west-2")

bot_table_name = os.environ.get("BOT_TABLE_NAME", "")
dynamodb_resource = boto3.resource("dynamodb")
bot_table = dynamodb_resource.Table(bot_table_name)


def get_bot_info(bot_id: str):
    # Temporary Use
    # TODO: Update this.
    response = bot_table.scan()
    bots = response['Items']

    if len(bots) == 0:
        raise RuntimeError("No bots created")
    bot = bots[0]
    model_kwargs = bot["llm"]["model_kwargs"]
    model_kwargs["temperature"] = float(bot["llm"].get("temperature", "0.01"))
    model_kwargs["max_tokens"] = int(bot["llm"].get("max_tokens", "4096"))
    # print(bot)
    return bot


@chatbot_lambda_call_wrapper
def lambda_handler(event_body: dict, context: dict):
    logger.info(json.dumps(event_body, indent=2))

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
    event_body["chatbot_config"] = get_bot_info(bot_id)
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

    # debuging
    # show debug info directly in local mode
    if is_running_local():
        response: dict = executor.run(event_body)
        r = process_response(event_body, response)
        if not stream:
            return r
        return "All records have been processed"
    else:
        try:
            response: dict = executor.run(event_body)
            r = process_response(event_body, response)
            if not stream:
                return r
            return "All records have been processed"
        except Exception as e:
            msg = traceback.format_exc()
            logger.exception("Main exception:%s" % msg)
            return "An exception has occurred"
