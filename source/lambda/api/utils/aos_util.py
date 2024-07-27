import os
import json
import boto3
import hashlib
from utils.secret_util import get_secret_value
from requests.auth import HTTPBasicAuth
from model.intention import Intention
from utils.embedding_util import append_embeddings, get_embedding_result
from aws_lambda_powertools import Logger
from opensearchpy import RequestsHttpConnection
from opensearchpy import OpenSearch

aos_domain_name = os.environ.get("AOS_DOMAIN_NAME", "smartsearch")
secret_name = os.environ.get("AOS_SECRET_NAME", "opensearch-master-user")
region = os.environ.get("AWS_REGION")

secret = json.loads(get_secret_value(secret_name))
username = secret.get("username")
password = secret.get("password")

HTTPS_PORT_NUMBER = "443"

headers = {"Content-Type": "application/json"}

logger = Logger()


class AOSUtil:
    def __init__(self):
        self.opensearch_endpoint = self.get_aos_endpoint()
        self.aos_client = self.get_aos_client(
            self.opensearch_endpoint, HTTPS_PORT_NUMBER
        )

    def get_aos_endpoint(self):
        aos_client = boto3.client("opensearch")
        response = aos_client.describe_domain(DomainName=aos_domain_name)

        aos_endpoint = response["DomainStatus"]["Endpoint"]
        return aos_endpoint

    def get_aos_client(self, host, port):
        client = OpenSearch(
            hosts=[{"host": host, "port": port}],
            http_auth=HTTPBasicAuth(username, password),
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
        )
        return client

    def add_doc(self, index: str, emb_model_id: str, intention: Intention):
        doc: dict = {
            "text": intention.question,
            "metadata": {
                "source": "api",
                "answer": intention.answer,
                "kwargs": intention.kwargs,
                "type": intention.type,
            },
        }

        appended_doc = append_embeddings(emb_model_id, index, self.opensearch_endpoint, HTTPBasicAuth(username, password), doc)

        self.aos_client.create(index, hashlib.md5(str(appended_doc).encode('utf-8')).hexdigest(), appended_doc)
        

    def list_doc(self, index: str, start_from: int, size: int):
        intention_list = []

        search_body = {"query": {"match_all": {}}}

        result = self.aos_client.search(
            body=search_body,
            index=index,
            params={"from": start_from, "size": size},
            headers=headers,
        )

        hits = result.get("hits")

        for hit in hits.get("hits"):
            print(hit["_source"])
            intention_dict = {}
            intention_dict["_id"] = hit.get("_id")
            source = hit.get("_source")
            intention_dict["text"] = source.get("text")
            metadata = source.get("metadata")
            intention_dict["answer"] = metadata.get("intent")
            intention_dict["kwargs"] = metadata.get("kwargs")
            intention_dict["type"] = metadata.get("type")
            intention_list.append(intention_dict)

        return intention_list

    def update_doc(self, index: str, emb_model_id: str, body: dict, intention_id: str):
        question = body.get("question")
        answer = body.get("answer")

        vector = get_embedding_result(emb_model_id, index, self.opensearch_endpoint, HTTPBasicAuth(username, password), question)

        new_doc = {"doc": {"text": question, "metadata": {"answer": answer}, "vector_field":vector}}

        response = self.aos_client.update(index=index, id=intention_id, body=new_doc)

        return response

    def delete_doc(self, index: str, intention_id: str):
        response = self.aos_client.delete(index=index, id=intention_id)

        return response
