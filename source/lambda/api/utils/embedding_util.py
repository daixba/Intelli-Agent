from typing import List

import boto3
from langchain.docstore.document import Document
from langchain_community.vectorstores import OpenSearchVectorSearch
from langchain_community.vectorstores.opensearch_vector_search import (
    OpenSearchVectorSearch,
)
from tenacity import retry, stop_after_attempt, wait_exponential
from langchain.embeddings.bedrock import BedrockEmbeddings

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))   
def create_aos_ingestion(model_id: str, docsearch: OpenSearchVectorSearch, documents: List[Document]) -> None:
    texts = [doc.page_content for doc in documents]
    metadatas = [doc.metadata for doc in documents]
    embeddings_vectors = docsearch.embedding_function.embed_documents(
        list(texts)
    )

    if isinstance(embeddings_vectors[0], dict):
        embeddings_vectors_list = []
        metadata_list = []
        for doc_id, metadata in enumerate(metadatas):
            embeddings_vectors_list.append(
                embeddings_vectors[0]["dense_vecs"][doc_id]
            )
            metadata["embedding_model_id"] = model_id
            metadata_list.append(metadata)
        embeddings_vectors = embeddings_vectors_list
        metadatas = metadata_list
    docsearch._OpenSearchVectorSearch__add(
        texts, embeddings_vectors, metadatas=metadatas
    )

def get_embedding_function(region_name: str, model_id: str) -> BedrockEmbeddings:
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