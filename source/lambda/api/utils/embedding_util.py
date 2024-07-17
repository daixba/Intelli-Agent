import json
from typing import Dict, List

import boto3
from langchain.docstore.document import Document
from langchain_community.vectorstores import OpenSearchVectorSearch
from langchain_community.vectorstores.opensearch_vector_search import (
    OpenSearchVectorSearch,
)
from tenacity import retry, stop_after_attempt, wait_exponential
from langchain.embeddings.sagemaker_endpoint import EmbeddingsContentHandler
from langchain.embeddings.bedrock import BedrockEmbeddings

class vectorContentHandler(EmbeddingsContentHandler):
    content_type = "application/json"
    accepts = "application/json"

    def transform_input(self, inputs: List[str], model_kwargs: Dict) -> bytes:
        input_str = json.dumps({"inputs": inputs, **model_kwargs})
        return input_str.encode("utf-8")

    def transform_output(self, output: bytes) -> List[List[float]]:
        response_json = json.loads(output.read().decode("utf-8"))
        return response_json["sentence_embeddings"]

class OpenSearchIngestionWorker:
    def __init__(
        self,
        docsearch: OpenSearchVectorSearch,
        model_id: str
    ):
        self.docsearch = docsearch
        self.model_id = model_id

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10)
    )   
    def aos_ingestion(self, documents: List[Document]) -> None:
        texts = [doc.page_content for doc in documents]
        metadatas = [doc.metadata for doc in documents]
        embeddings_vectors = self.docsearch.embedding_function.embed_documents(
            list(texts)
        )

        if isinstance(embeddings_vectors[0], dict):
            embeddings_vectors_list = []
            metadata_list = []
            for doc_id, metadata in enumerate(metadatas):
                embeddings_vectors_list.append(
                    embeddings_vectors[0]["dense_vecs"][doc_id]
                )
                metadata["embedding_model_id"] = self.model_id
                metadata_list.append(metadata)
            embeddings_vectors = embeddings_vectors_list
            metadatas = metadata_list
        self.docsearch._OpenSearchVectorSearch__add(
            texts, embeddings_vectors, metadatas=metadatas
        )

def getEmbeddingFunction(region_name: str, model_id: str) -> BedrockEmbeddings:
    client = boto3.client(
            "bedrock-runtime",
            region_name=region_name
            )
    embeddings = BedrockEmbeddings(
        client=client,
        model_id=model_id,
        normalize=True
    )
    return embeddings   