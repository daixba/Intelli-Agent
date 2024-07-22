import json
import os

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext
from utils.secret_util import get_secret_value
from utils.aos_util import AOSUtil
from model.model import Intention, BotVersion, Pagination
from utils.common import paginate_from

opensearch_endpoint = os.environ.get("OPENSEARCH_ENDPOINT", "")
secret_name = os.environ.get('AOS_SECRET_NAME')
region = os.environ.get("AWS_REGION")

tracer = Tracer()
logger = Logger()
app = APIGatewayRestResolver()

secret = json.loads(get_secret_value(secret_name))
username = secret.get("username")
password = secret.get("password")

aos_util = AOSUtil()

@app.post("/v1/bots/<bot_id>/intentions")
@tracer.capture_method
def create_intention(bot_id: str):
    body: dict = app.current_event.json_body
    logger.info(body)
    intention_body = Intention(question=body['question'], answer=body['answer'])
    logger.info(intention_body.model_dump())
    
    aos_util.add_doc(bot_id, intention_body)
    logger.info("ingested")

    return {
        'statusCode': 200,
        'body': 'Success!'
    }
    

@app.get("/v1/bots/<bot_id>/intentions")
@tracer.capture_method
def get_intention(bot_id: str):
    body: dict = app.current_event.json_body
    logger.info(body)
    pagination_body = Pagination(page=body['page'], size=body['size'])
    logger.info(pagination_body.model_dump())

    page = pagination_body.page
    size = pagination_body.size

    start_from = paginate_from(page, size)
    
    intention_list = aos_util.list_doc(bot_id, BotVersion.TEST, start_from, size)
    
    return intention_list


@app.post("/v1/bots/<bot_id>/intentions/<intention_id>")
@tracer.capture_method
def update_intention(bot_id: str, intention_id: str):    
    body: dict = app.current_event.json_body
    logger.info(body)

    aos_util.update_doc(bot_id, BotVersion.TEST, body, intention_id)

    return {
        'statusCode': 200,
        'body': "Updated"
    }
    
    
@app.delete("/v1/bots/<bot_id>/intentions/<intention_id>")
@tracer.capture_method
def delete_intention(bot_id: str, intention_id: str):    
    body: dict = app.current_event.json_body
    logger.info(body)
    
    aos_util.delete_doc(bot_id, BotVersion.TEST, intention_id)
    
    return {
        'statusCode': 200,
        'body': "Deleted"
    }

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)
