import os
import json
import uuid
import boto3
import traceback

from common_logic.common_utils.ddb_utils import DynamoDBChatMessageHistory
# from main_utils.online_entries import get_entry
from utils.response_utils import process_response
from common_logic.common_utils.constant import EntryType
from common_logic.common_utils.logger_utils import get_logger
from common_logic.common_utils.websocket_utils import load_ws_client
from common_logic.common_utils.lambda_invoke_utils import (
    chatbot_lambda_call_wrapper,
    is_running_local,
)
from utils import executor
from botocore.exceptions import ClientError

logger = get_logger("main")

session_table_name = os.environ.get("SESSION_TABLE_NAME", "")
message_table_name = os.environ.get("MESSAGE_TABLE_NAME", "")

websocket_url = os.environ.get("WEBSOCKET_URL", "")
openai_key_arn = os.environ.get("OPENAI_KEY_ARN", "")
region_name = os.environ["AWS_REGION"]
session = boto3.session.Session()
secret_manager_client = session.client(
    service_name="secretsmanager",
    region_name=region_name
)
bot_table_name = os.environ.get("BOT_TABLE_NAME", "")
dynamodb_resource = boto3.resource("dynamodb")
bot_table = dynamodb_resource.Table(bot_table_name)


# def get_prompt(user_id: str, model_id: str, task_type: str):
#     response = prompt_table.get_item(
#             Key={"userId": user_id, "sortKey": f"{model_id}__{task_type}"}
#         )
#     item = response.get("Item")
#     if item:
#         return item.get("prompt")
#     return None


# def get_secret_value(secret_arn: str):
#     """Get secret value from secret manager
#
#     Args:
#         secret_arn (str): secret arn
#
#     Returns:
#         str: secret value
#     """
#     try:
#         get_secret_value_response = secret_manager_client.get_secret_value(
#             SecretId=secret_arn
#         )
#     except ClientError as e:
#         raise Exception("Fail to retrieve the secret value: {}".format(e))
#     else:
#         if "SecretString" in get_secret_value_response:
#             secret = get_secret_value_response["SecretString"]
#             return secret
#         else:
#             raise Exception("Fail to retrieve the secret value")


@chatbot_lambda_call_wrapper
def lambda_handler(event_body: dict, context: dict):
    print("Main ", ">" * 20)
    logger.info(json.dumps(event_body, indent=2))

    stream = context['stream']
    request_timestamp = context['request_timestamp']
    ws_connection_id = context.get('ws_connection_id')
    if stream:
        load_ws_client(websocket_url)

    client_type = event_body.get("client_type", "default_client_type")
    entry_type = event_body.get("entry_type", EntryType.COMMON).lower()
    session_id = event_body.get("session_id", None)
    custom_message_id = event_body.get("custom_message_id", "")
    user_id = event_body.get("user_id", "default_user_id")
    # TODO Need to modify key
    # group_name = event_body.get("chatbot_config").get("default_workspace_config", {"rag_workspace_ids": ["Admin"]}).get(
    #     "rag_workspace_ids", "Admin")[0]
    group_name = "Admin"

    if not session_id:
        session_id = f"session_{int(request_timestamp)}"

    print(message_table_name)
    print(session_table_name)

    ddb_history_obj = DynamoDBChatMessageHistory(
        sessions_table_name=session_table_name,
        messages_table_name=message_table_name,
        session_id=session_id,
        user_id=user_id,
        client_type=client_type,
    )

    chat_history = ddb_history_obj.messages_as_langchain

    logger.info(f'chat_history:\n{json.dumps(chat_history, ensure_ascii=False, indent=2)}')

    event_body['stream'] = stream
    event_body["chat_history"] = chat_history
    event_body["ws_connection_id"] = ws_connection_id
    event_body['custom_message_id'] = custom_message_id
    event_body['ddb_history_obj'] = ddb_history_obj
    event_body['request_timestamp'] = request_timestamp
    event_body['chatbot_config']['user_id'] = user_id
    event_body['chatbot_config']['group_name'] = group_name

    event_body['message_id'] = str(uuid.uuid4())
    # event_body['chatbot_config']['prompt_templates'] = get_prompt(user_id,
    #                             event_body['chatbot_config']['default_llm_config']['model_id'],
    #                             event_body['chatbot_config']['chatbot_mode'])

    # logger.info(f"event_body:\n{json.dumps(event_body,ensure_ascii=False,indent=2,cls=JSONEncoder)}")

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
