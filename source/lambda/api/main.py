# import requests
# from requests import Response

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext

tracer = Tracer()
logger = Logger()
app = APIGatewayRestResolver()

test_bots = [
    {
        "name": "test",
        "description": "Test Bot",
        "knowledge_base_retrievers": [{
            "index": "test-qa",
            "retrieve": {
                "top-k": 3
            }
        }],
        "intention_retrievers": [{
            "index": "test-intent"
        }],
        "model": {
            "type": "Bedrock",
            "model_id": "anthropic.claude-3-sonnet-20240229-v1:0"
        },
        "embedding": {
            "type": "Bedrock",
            "model_id": "cohere.embed-english-v3"
        },
        "prompts": [
            {
                "name": "RAG_PROMPT",
                "text": "You are a helpful assistant."
            }
        ],
        "available_tools": [
            {
                "name": "QA",
                "default": True
            }
        ]
    }]


@app.get("/v1/bots")
@tracer.capture_method
def get_bots():
    # placeholder
    return {"bots": test_bots}


# You can continue to use other utilities just as before
@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)
