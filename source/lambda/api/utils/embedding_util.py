
import os
import boto3
from langchain.embeddings.bedrock import BedrockEmbeddings

region = os.environ.get("AWS_REGION")
bedrock_client = boto3.client("bedrock-runtime",region_name=region)

def get_embedding_result(emb_model_id, text_input):
        
        embedding_func = BedrockEmbeddings(
            client=bedrock_client,
            model_id=emb_model_id,
            normalize=True
        )
        
        embeddings_vectors = embedding_func.embed_documents(
            [text_input]
        )
        
        return embeddings_vectors

def append_embeddings(emb_model_id, intention_body):
        document = {}
        question = intention_body.question
        answer = intention_body.answer
        kwargs = intention_body.kwargs
        vector = get_embedding_result(emb_model_id, question)
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