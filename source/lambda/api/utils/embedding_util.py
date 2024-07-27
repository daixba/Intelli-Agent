
import os
import boto3
from opensearchpy import RequestsHttpConnection
from langchain_community.vectorstores import OpenSearchVectorSearch
from langchain_community.vectorstores.opensearch_vector_search import (
    OpenSearchVectorSearch,
)
from langchain.embeddings.bedrock import BedrockEmbeddings

region = os.environ.get("AWS_REGION")
bedrock_client = boto3.client("bedrock-runtime",region_name=region)

def get_embedding_result(emb_model_id, index_name, aos_endpoint, auth, text_input):
        
        embedding_func = BedrockEmbeddings(
            client=bedrock_client,
            model_id=emb_model_id,
            normalize=True
        )
        
        docsearch = OpenSearchVectorSearch(
            index_name=index_name,
            embedding_function=embedding_func,
            opensearch_url=f"https://{aos_endpoint}",
            http_auth=auth,
            timeout=300,
            use_ssl=True,
            verify_certs=True,
            connection_class=RequestsHttpConnection,
        )
        
        embeddings_vectors = docsearch.embedding_function.embed_documents(
            list(text_input)
        )
        
        return embeddings_vectors

def append_embeddings(emb_model_id, index_name, aos_endpoint, auth, intention_body):
        document = {}
        question = intention_body.get("question")
        answer = intention_body.get("answer")
        kwargs = intention_body.get("kwargs")
        vector = get_embedding_result(emb_model_id, index_name, aos_endpoint, auth, question)
        document = { 
                "text" : question,
                "metadata" : {
                    "answer": answer,
                    "source": "api",
                    "kwargs": kwargs,
                    "type": "Intent"
                    },
                "vector_field" : vector[0]
            }
        
        return document