import json
import requests
import os

from langchain.docstore.document import Document
from langchain_community.vectorstores import OpenSearchVectorSearch
from langchain_community.vectorstores.opensearch_vector_search import (
    OpenSearchVectorSearch,
)
from opensearchpy import RequestsHttpConnection

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext
from utils.embedding_util import OpenSearchIngestionWorker, getEmbeddingFunction
from utils.ddb_util import get_table_item
from utils.secret_util import get_secret_value
from requests.auth import HTTPBasicAuth
from utils.aos_util import AOSUtil

opensearch_endpoint = os.environ.get("OPENSEARCH_ENDPOINT", "")
secret_name = os.environ.get('AOS_SECRET_NAME')
region = os.environ.get("AWS_REGION")

tracer = Tracer()
logger = Logger()
app = APIGatewayRestResolver()

secret = json.loads(get_secret_value(secret_name))
username = secret.get("username")
password = secret.get("password")

# TODO: add pydantic model
@app.post("/v1/bots/<bot_id>/intentions")
@tracer.capture_method
def post_intention(bot_id: str):
    body: dict = app.current_event.json_body

    item = get_table_item(id=bot_id, version="v1")
    intention_retrievers = item.get("intention_retrievers")

    index = intention_retrievers[0].get("index")
    print("index")
    print(index)

    embedding = intention_retrievers[0].get("embedding")
    model_type = embedding.get("type")
    print("model_type")
    print(model_type)

    model_id = embedding.get("model_id")
    print("model_id")
    print(model_id)
    
    question = body.get("question")
    answer = body.get("answer")
    intention = answer.get("intent", "")
    keyword_argument = answer.get("kwargs","")
    
    doc = Document(page_content=question, metadata={'content_type': 'paragraph', 'heading_hierarchy': {'size': 1}, 'file_path': 'balabala', 'keywords': [], 'summary': '', 'jsonlAnswer': {'intent': intention, 'kwargs': keyword_argument}})
 
    embedding_function = getEmbeddingFunction(
        region,
        model_id
    )
    
    docsearch = OpenSearchVectorSearch(
        index_name=index,
        embedding_function=embedding_function,
        opensearch_url=opensearch_endpoint,
        http_auth=(username, password),
        timeout=300,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )
    
    ingestion_worker = OpenSearchIngestionWorker(docsearch, model_id)
    ingestion_worker.aos_ingestion([doc])
    print("ingested")

    return {
        'statusCode': 200,
        'body': 'Success!'
    }
    

@app.get("/v1/bots/<bot_id>/intentions")
@tracer.capture_method
def get_intention(bot_id: str):
    body: dict = app.current_event.json_body
    print(body)

    aos_util = AOSUtil(bot_id,"v1")
    
    response = aos_util.list_doc()
    
    list = []
    if response.status_code == 200:
        result = response.json()
        hits = result.get("hits")
        if len(hits) == 0:
            return {
                'statusCode': 200,
                'body': "Empty Index"
            }
        
        for hit in hits.get("hits"):
            dict={}
            dict["_id"] = hit.get("_id")
            source=hit.get("_source")
            dict["text"] = source.get("text")
            meta=source.get("metadata")
            jsonlAnswer=meta.get("jsonlAnswer")
            dict["intent"] = jsonlAnswer.get("intent")
            dict["kwargs"] = jsonlAnswer.get("kwargs")
            print(dict)
            list.append(dict)
        print(list)
        return {
            'statusCode': 200,
            'body': list
        }
    else:
        print(f"Failed to retrieve documents: {response.status_code} - {response.text}")
        return {
            'statusCode': response.status_code,
            'body': response.text
        }


@app.post("/v1/bots/<bot_id>/intentions/<intention_id>")
@tracer.capture_method
def update_intention(bot_id: str, intention_id: str):    
    body: dict = app.current_event.json_body
    print(body)

    aos_util = AOSUtil(bot_id,"v1")

    aos_util.update_doc(body, intention_id)

    return {
        'statusCode': 200,
        'body': "Updated"
    }
    
    
@app.delete("/v1/bots/<bot_id>/intentions/<intention_id>")
@tracer.capture_method
def delete_intention(bot_id: str, intention_id: str):    
    body: dict = app.current_event.json_body
    print(body)

    aos_util = AOSUtil(bot_id,"v1")
    
    aos_util.delete_doc(intention_id)
    
    return {
        'statusCode': 200,
        'body': "Deleted"
    }

@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext) -> dict:
    return app.resolve(event, context)
