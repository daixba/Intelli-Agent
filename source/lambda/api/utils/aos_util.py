import os
import json
import requests
from utils.ddb_util import get_table_item
from utils.secret_util import get_secret_value
from requests.auth import HTTPBasicAuth

opensearch_endpoint = os.environ.get("OPENSEARCH_ENDPOINT", "")
secret_name = os.environ.get('AOS_SECRET_NAME')
region = os.environ.get("AWS_REGION")

secret = json.loads(get_secret_value(secret_name))
username = secret.get("username")
password = secret.get("password")

headers = {'Content-Type': 'application/json'}

class AOSUtil:
    def __init__(
        self,
        bot_id: str,
        version: str
    ):
        self.bot_id = bot_id
        self.version = version

    def get_index(self, bot_id: str, version: str):
        item = get_table_item(id=bot_id, version=version)
        intention_retrievers = item.get("intention_retrievers")
        print("intention_retrievers")
        print(intention_retrievers)
        index = intention_retrievers[0].get("index")
        return index
    

    def list_doc(self):

        index = self.get_index(self.bot_id, self.version)
        
        url = f'{opensearch_endpoint}/{index}/_search'
        
        print(url)
        
        response = requests.get(url, params={'size': 999}, headers=headers, auth=HTTPBasicAuth(username, password))

        return response

    def update_doc(self, body: dict, intention_id: str):

        index = self.get_index(self.bot_id, self.version)
        
        url = f'{opensearch_endpoint}/{index}/_update/{intention_id}'
        
        print(url)
        question = body.get("question")
        answer = body.get("answer")
        new_doc = {"doc": {"text": question, "metadata": {"jsonlAnswer": answer}}}

        response = requests.post(url, json=new_doc, headers=headers, auth=HTTPBasicAuth(username, password))

        return response

    def delete_doc(self, intention_id: str):

        index = self.get_index(self.bot_id, self.version)
        
        url = f'{opensearch_endpoint}/{index}/_doc/{intention_id}'
        
        print(url)

        response = requests.delete(url, headers=headers, auth=HTTPBasicAuth(username, password))

        return response