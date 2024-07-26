import os
import json
import boto3
import logging
import traceback
import asyncio
from typing import Any, Dict, List

from langchain.schema.retriever import BaseRetriever
from langchain.callbacks.manager import CallbackManagerForRetrieverRun
from langchain.docstore.document import Document
from langchain_community.embeddings import BedrockEmbeddings

from common_logic.common_utils.time_utils import timeit
from .aos_utils import LLMBotOpenSearchClient

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# region = os.environ["AWS_REGION"]
aos_endpoint = os.environ.get("AOS_ENDPOINT", "")
aos_domain_name = os.environ.get("AOS_DOMAIN_NAME", "smartsearch")
aos_secret = os.environ.get("AOS_SECRET_NAME", "opensearch-master-user")

sm_client = boto3.client("secretsmanager")
master_user = sm_client.get_secret_value(SecretId=aos_secret)["SecretString"]

DEFAULT_TEXT_FIELD_NAME = "text"
DEFAULT_VECTOR_FIELD_NAME = "vector_field"
DEFAULT_SOURCE_FIELD_NAME = "source"

if not aos_endpoint:
    aos_client = boto3.client("opensearch")
    response = aos_client.describe_domain(DomainName=aos_domain_name)

    aos_endpoint = response["DomainStatus"]["Endpoint"]
cred = json.loads(master_user)
username = cred.get("username")
password = cred.get("password")
auth = (username, password)
aos_client = LLMBotOpenSearchClient(aos_endpoint, auth)


def remove_redundancy_debug_info(results):
    # filtered_results = copy.deepcopy(results)
    filtered_results = results
    for result in filtered_results:
        for field in list(result["detail"].keys()):
            if field.endswith("embedding") or field.startswith("vector"):
                del result["detail"][field]
    return filtered_results


@timeit
def get_similarity_embedding(
        query: str,
        embedding_model_id: str,
        target_model: str = "",
        model_type: str = "vector",
):
    # query_similarity_embedding_prompt = query
    # response = SagemakerEndpointVectorOrCross(
    #     prompt=query_similarity_embedding_prompt,
    #     endpoint_name=embedding_model_endpoint,
    #     model_type=model_type,
    #     stop=None,
    #     region_name=None,
    #     target_model=target_model
    # )
    # return response
    # if model_type in ["vector","m3"]:
    #     response = {"dense_vecs": response}
    # # elif model_type == "m3":
    # #     # response["dense_vecs"] = response["dense_vecs"]
    # #     response = {"dense_vecs": response}
    # return response

    embeddings = BedrockEmbeddings(
        # region_name="us-west-2",
        model_id=embedding_model_id,
    )
    query_result = embeddings.embed_query(query)
    return query_result


def get_filter_list(parsed_query: dict):
    filter_list = []
    if "is_api_query" in parsed_query and parsed_query["is_api_query"]:
        filter_list.append({"term": {"metadata.is_api": True}})
    return filter_list


def get_faq_answer(source, index_name, source_field):
    opensearch_query_response = aos_client.search(
        index_name=index_name,
        query_type="basic",
        query_term=source,
        field=f"metadata.{source_field}",
    )
    for r in opensearch_query_response["hits"]["hits"]:
        if (
                "field" in r["_source"]["metadata"]
                and "answer" == r["_source"]["metadata"]["field"]
        ):
            return r["_source"]["content"]
        elif "jsonlAnswer" in r["_source"]["metadata"]:
            return r["_source"]["metadata"]["jsonlAnswer"]["answer"]
    return ""


def get_faq_content(source, index_name):
    opensearch_query_response = aos_client.search(
        index_name=index_name,
        query_type="basic",
        query_term=source,
        field="metadata.source",
    )
    for r in opensearch_query_response["hits"]["hits"]:
        if r["_source"]["metadata"]["field"] == "all_text":
            return r["_source"]["content"]
    return ""


def get_doc(file_path, index_name):
    opensearch_query_response = aos_client.search(
        index_name=index_name,
        query_type="basic",
        query_term=file_path,
        field="metadata.file_path",
        size=100,
    )
    chunk_list = []
    chunk_id_set = set()
    for r in opensearch_query_response["hits"]["hits"]:
        try:
            if "chunk_id" not in r["_source"]["metadata"] or not r["_source"][
                "metadata"
            ]["chunk_id"].startswith("$"):
                continue
            chunk_id = r["_source"]["metadata"]["chunk_id"]
            content_type = r["_source"]["metadata"]["content_type"]
            chunk_group_id = int(chunk_id.split("-")[0].strip("$"))
            chunk_section_id = int(chunk_id.split("-")[-1])
            if (chunk_id, content_type) in chunk_id_set:
                continue
        except Exception as e:
            logger.error(traceback.format_exc())
            continue
        chunk_id_set.add((chunk_id, content_type))
        chunk_list.append(
            (
                chunk_id,
                chunk_group_id,
                content_type,
                chunk_section_id,
                r["_source"]["text"],
            )
        )
    sorted_chunk_list = sorted(chunk_list, key=lambda x: (x[1], x[2], x[3]))
    chunk_text_list = [x[4] for x in sorted_chunk_list]
    return "\n".join(chunk_text_list)


def organize_faq_results(
        response, index_name, source_field="file_path", text_field="text"
):
    """
    Organize results from aos response

    :param query_type: query type
    :param response: aos response json
    """
    results = []
    if not response:
        return results
    aos_hits = response["hits"]["hits"]
    for aos_hit in aos_hits:
        result = {}
        try:
            result["score"] = aos_hit["_score"]
            data = aos_hit["_source"]
            metadata = data["metadata"]
            if "field" in metadata:
                result["answer"] = get_faq_answer(
                    result["source"], index_name, source_field
                )
                result["content"] = aos_hit["_source"]["content"]
                result["question"] = aos_hit["_source"]["content"]
                result[source_field] = aos_hit["_source"]["metadata"][source_field]
            elif "answer" in metadata:
                # Intentions
                result["answer"] = metadata["answer"]
                result["question"] = data["text"]
                result["content"] = data["text"]
                result["source"] = metadata[source_field]
                result["kwargs"] = metadata.get("kwargs", {})
            else:
                result["answer"] = aos_hit["_source"]["metadata"]
                result["content"] = aos_hit["_source"][text_field]
                result["question"] = aos_hit["_source"][text_field]
                result[source_field] = aos_hit["_source"]["metadata"][source_field]
        except:
            logger.info("index_error")
            logger.info(traceback.format_exc())
            logger.info(aos_hit["_source"])
            continue
        # result.update(aos_hit["_source"])
        results.append(result)
    return results


class QueryQuestionRetriever(BaseRetriever):
    index: Any
    vector_field: Any
    text_field: Any
    source_field: Any
    top_k: Any
    lang: Any
    embedding_model_id: Any
    # target_model: Any
    model_type: Any
    query_key: str = "query"
    enable_debug: Any

    def __init__(
            self,
            retriever_config: Dict,
            top_k: int = 3,
            query_key="query",
            enable_debug=False,
    ):
        super().__init__()

        self.index = retriever_config["index"]
        self.vector_field = retriever_config["config"].get(
            "vector_field_name", DEFAULT_VECTOR_FIELD_NAME
        )
        self.text_field = retriever_config["config"].get(
            "text_field_name", DEFAULT_TEXT_FIELD_NAME
        )
        self.source_field = retriever_config["config"].get(
            "source_field_name", DEFAULT_SOURCE_FIELD_NAME
        )
        self.top_k = int(retriever_config["config"].get("top_k", "3"))
        # self.lang = workspace["languages"][0]
        self.lang = "English"
        self.embedding_model_id = retriever_config["embedding"]["model_id"]
        # if workspace["embeddings_model_name"].endswith("tar.gz"):
        #     self.target_model = workspace["embeddings_model_name"]
        # else:
        #     self.target_model = None
        # self.target_model = None
        # self.model_type = workspace["model_type"]
        self.model_type = retriever_config["embedding"]["type"]
        self.query_key = query_key
        self.enable_debug = enable_debug

    @timeit
    def _get_relevant_documents(
            self, question: Dict, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        query = question[self.query_key]
        debug_info = question["debug_info"]
        opensearch_knn_results = []
        query_repr = get_similarity_embedding(query, self.embedding_model_id)
        opensearch_knn_response = aos_client.search(
            index_name=self.index,
            query_type="knn",
            query_term=query_repr,
            field=self.vector_field,
            size=self.top_k,
        )
        opensearch_knn_results.extend(
            organize_faq_results(
                opensearch_knn_response, self.index, self.source_field, self.text_field
            )
        )
        docs = []
        for result in opensearch_knn_results:
            docs.append(
                Document(
                    page_content=result["content"],
                    metadata={
                        "source": result[self.source_field],
                        "score": result["score"],
                        "retrieval_score": result["score"],
                        "retrieval_content": result["content"],
                        "answer": result["answer"],
                        "question": result["question"],
                        "kwargs": result.get("kwargs", {}),
                    },
                )
            )

        if self.enable_debug:
            debug_info[f"qq-knn-recall-{self.index}-{self.lang}"] = (
                remove_redundancy_debug_info(opensearch_knn_results)
            )
        return docs


class QueryDocumentKNNRetriever(BaseRetriever):
    index: Any
    vector_field: Any
    text_field: Any
    source_field: Any
    top_k: Any
    lang: Any
    embedding_model_id: Any
    using_whole_doc: Any
    context_num: Any
    # target_model: Any
    query_key: str = "query"
    enable_debug: Any

    def __init__(
            self,
            retriever_config: Dict,
            using_whole_doc=False,
            context_num=5,
            top_k=3,
            query_key="query",
            enable_debug=False,
    ):
        super().__init__()
        # self.index = workspace["open_search_index_name"]
        # self.vector_field = "vector_field"
        # self.source_field = "file_path"
        # self.text_field = "text"
        # self.lang = workspace["languages"][0]
        # self.embedding_model_endpoint = workspace["embeddings_model_endpoint"]
        # if workspace["embeddings_model_name"].endswith("tar.gz"):
        #     self.target_model = workspace["embeddings_model_name"]
        # else:
        #     self.target_model = None
        # self.model_type = workspace["model_type"]
        self.index = retriever_config["index"]
        self.vector_field = retriever_config["config"].get(
            "vector_field_name", DEFAULT_VECTOR_FIELD_NAME
        )
        self.text_field = retriever_config["config"].get(
            "text_field_name", DEFAULT_TEXT_FIELD_NAME
        )
        self.source_field = retriever_config["config"].get(
            "source_field_name", DEFAULT_SOURCE_FIELD_NAME
        )
        self.top_k = int(retriever_config["config"].get("top_k", "3"))
        # self.lang = workspace["languages"][0]
        self.lang = "English"
        self.embedding_model_id = retriever_config["embedding"]["model_id"]
        self.using_whole_doc = using_whole_doc
        self.context_num = context_num
        self.query_key = query_key
        self.enable_debug = enable_debug

    # async def __ainvoke_get_context(self, aos_hit, window_size, loop):
    #     return await loop.run_in_executor(None,
    #                                       get_context,
    #                                       aos_hit,
    #                                       self.index,
    #                                       window_size)
    #
    # async def __spawn_task(self, aos_hits, context_size):
    #     loop = asyncio.get_event_loop()
    #     task_list = []
    #     for aos_hit in aos_hits:
    #         if context_size:
    #             task = asyncio.create_task(
    #                 self.__ainvoke_get_context(
    #                     aos_hit,
    #                     context_size,
    #                     loop))
    #             task_list.append(task)
    #     return await asyncio.gather(*task_list)

    @timeit
    def organize_results(
            self,
            response,
            aos_index=None,
            source_field="file_path",
            text_field="text",
            using_whole_doc=True,
            context_size=0,
    ):
        """
        Organize results from aos response

        :param query_type: query type
        :param response: aos response json
        """
        results = []
        if not response:
            return results
        aos_hits = response["hits"]["hits"]
        if len(aos_hits) == 0:
            return results
        for aos_hit in aos_hits:
            result = {"data": {}}
            source = aos_hit["_source"]["metadata"][source_field]
            result["source"] = source
            result["score"] = aos_hit["_score"]
            result["detail"] = aos_hit["_source"]
            # result["content"] = aos_hit['_source'][text_field]
            result["content"] = aos_hit["_source"][text_field]
            result["doc"] = result["content"]
            # if 'additional_vecs' in aos_hit['_source']['metadata'] and \
            #     'colbert_vecs' in aos_hit['_source']['metadata']['additional_vecs']:
            #     result["data"]["colbert"] = aos_hit['_source']['metadata']['additional_vecs']['colbert_vecs']
            results.append(result)
        # if using_whole_doc:
        #     for result in results:
        #         doc = get_doc(result["source"], aos_index)
        #         if doc:
        #             result["doc"] = doc
        # else:
        #     response_list = asyncio.run(self.__spawn_task(aos_hits, context_size))
        #     for context, result in zip(response_list, results):
        #         result["doc"] = "\n".join(context[0] + [result["doc"]] + context[1])
        # context = get_context(aos_hit['_source']["metadata"]["heading_hierarchy"]["previous"],
        #                     aos_hit['_source']["metadata"]["heading_hierarchy"]["next"],
        #                     aos_index,
        #                     context_size)
        # if context:
        #     result["doc"] = "\n".join(context[0] + [result["doc"]] + context[1])
        return results

    @timeit
    def __get_knn_results(self, query_term, filter):
        opensearch_knn_response = aos_client.search(
            index_name=self.index,
            query_type="knn",
            query_term=query_term,
            field=self.vector_field,
            size=self.top_k,
            filter=filter,
        )
        opensearch_knn_results = self.organize_results(
            opensearch_knn_response,
            self.index,
            self.source_field,
            self.text_field,
            self.using_whole_doc,
            self.context_num,
        )[: self.top_k]
        return opensearch_knn_results

    @timeit
    def _get_relevant_documents(
            self, question: Dict, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        query = question[self.query_key]
        if (
                "query_lang" in question
                and question["query_lang"] != self.lang
                and "translated_text" in question
        ):
            query = question["translated_text"]
        debug_info = question["debug_info"]
        # query_repr = get_relevance_embedding(query, self.lang, self.embedding_model_endpoint, self.target_model,
        #                                      self.model_type)
        query_repr = get_similarity_embedding(query, self.embedding_model_id)
        # question["colbert"] = query_repr["colbert_vecs"][0]
        filter = get_filter_list(question)
        # 1. get AOS KNN results.
        opensearch_knn_results = self.__get_knn_results(query_repr, filter)
        final_results = opensearch_knn_results
        doc_list = []
        content_set = set()
        for result in final_results:
            if result["doc"] in content_set:
                continue
            content_set.add(result["content"])
            # TODO add jsonlans
            doc_list.append(
                Document(
                    page_content=result["doc"],
                    metadata={
                        "source": result["source"],
                        "retrieval_content": result["content"],
                        "retrieval_data": result["data"],
                        "retrieval_score": result["score"],
                        # "jsonlAnswer": result["detail"]["metadata"]["jsonlAnswer"],
                        #
                        # set common score for llm.
                        "score": result["score"],
                    },
                )
            )
        if self.enable_debug:
            debug_info[f"qd-knn-recall-{self.index}-{self.lang}"] = (
                remove_redundancy_debug_info(opensearch_knn_results)
            )
        return doc_list


class QueryDocumentBM25Retriever(BaseRetriever):
    index: Any
    vector_field: Any
    text_field: Any
    source_field: Any
    using_whole_doc: Any
    context_num: Any
    top_k: Any
    lang: Any
    # model_type: Any
    query_key: str = "query"
    enable_debug: Any
    config: Dict = {"run_name": "BM25"}

    def __init__(
            self,
            retriever_config: Dict,
            using_whole_doc=False,
            context_num=5,
            top_k=3,
            query_key="query",
            enable_debug=False,
    ):
        super().__init__()
        # self.index = workspace["open_search_index_name"]
        # self.vector_field = "vector_field"
        # self.source_field = "file_path"
        # self.text_field = "text"
        # self.lang = workspace["languages"][0]
        # self.model_type = workspace["model_type"]
        self.index = retriever_config["index"]
        self.vector_field = retriever_config["config"].get(
            "vector_field_name", DEFAULT_VECTOR_FIELD_NAME
        )
        self.text_field = retriever_config["config"].get(
            "text_field_name", DEFAULT_TEXT_FIELD_NAME
        )
        self.source_field = retriever_config["config"].get(
            "source_field_name", DEFAULT_SOURCE_FIELD_NAME
        )
        self.top_k = int(retriever_config["config"].get("top_k", "3"))
        self.using_whole_doc = using_whole_doc
        self.context_num = context_num
        # self.top_k = top_k
        self.query_key = query_key
        self.enable_debug = enable_debug

    # async def __ainvoke_get_context(self, aos_hit, window_size, loop):
    #     return await loop.run_in_executor(None,
    #                                       get_context,
    #                                       aos_hit,
    #                                       self.index,
    #                                       window_size)
    #
    # async def __spawn_task(self, aos_hits, context_size):
    #     loop = asyncio.get_event_loop()
    #     task_list = []
    #     for aos_hit in aos_hits:
    #         if context_size:
    #             task = asyncio.create_task(
    #                 self.__ainvoke_get_context(
    #                     aos_hit,
    #                     context_size,
    #                     loop))
    #             task_list.append(task)
    #     return await asyncio.gather(*task_list)

    @timeit
    def organize_results(
            self,
            response,
            aos_index=None,
            source_field="file_path",
            text_field="text",
            using_whole_doc=True,
            context_size=0,
    ):
        """
        Organize results from aos response

        :param query_type: query type
        :param response: aos response json
        """
        results = []
        if not response:
            return results
        aos_hits = response["hits"]["hits"]
        if len(aos_hits) == 0:
            return results
        for aos_hit in aos_hits:
            result = {"data": {}}
            source = aos_hit["_source"]["metadata"][source_field]

            result["source"] = source
            result["score"] = aos_hit["_score"]
            result["detail"] = aos_hit["_source"]
            # result["content"] = aos_hit['_source'][text_field]
            result["content"] = aos_hit["_source"][text_field]
            result["doc"] = result["content"]
            # if 'additional_vecs' in aos_hit['_source']['metadata'] and \
            #     'colbert_vecs' in aos_hit['_source']['metadata']['additional_vecs']:
            #     result["data"]["colbert"] = aos_hit['_source']['metadata']['additional_vecs']['colbert_vecs']
            if "jsonlAnswer" in aos_hit["_source"]["metadata"]:
                result["jsonlAnswer"] = aos_hit["_source"]["metadata"]["jsonlAnswer"]
            results.append(result)
        # if using_whole_doc:
        #     for result in results:
        #         doc = get_doc(result["source"], aos_index)
        #         if doc:
        #             result["doc"] = doc
        # else:
        #     response_list = asyncio.run(self.__spawn_task(aos_hits, context_size))
        #     for context, result in zip(response_list, results):
        #         result["doc"] = "\n".join(context[0] + [result["doc"]] + context[1])
        # context = get_context(aos_hit['_source']["metadata"]["heading_hierarchy"]["previous"],
        #                     aos_hit['_source']["metadata"]["heading_hierarchy"]["next"],
        #                     aos_index,
        #                     context_size)
        # if context:
        #     result["doc"] = "\n".join(context[0] + [result["doc"]] + context[1])
        return results

    @timeit
    def __get_bm25_results(self, query_term, filter):
        opensearch_bm25_response = aos_client.search(
            index_name=self.index,
            query_type="fuzzy",
            query_term=query_term,
            field=self.text_field,
            size=self.top_k,
            filter=filter,
        )
        opensearch_bm25_results = self.organize_results(
            opensearch_bm25_response,
            self.index,
            self.source_field,
            self.text_field,
            self.using_whole_doc,
            self.context_num,
        )[: self.top_k]
        return opensearch_bm25_results

    @timeit
    def _get_relevant_documents(
            self, question: Dict, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        query = question[self.query_key]
        if (
                "query_lang" in question
                and question["query_lang"] != self.lang
                and "translated_text" in question
        ):
            query = question["translated_text"]
        debug_info = question["debug_info"]
        # query_repr = get_relevance_embedding(query, self.lang, self.embedding_model_endpoint, self.model_type)
        # question["colbert"] = query_repr["colbert_vecs"][0]
        filter = get_filter_list(question)
        opensearch_bm25_results = self.__get_bm25_results(query, filter)
        final_results = opensearch_bm25_results
        doc_list = []
        content_set = set()
        for result in final_results:
            if result["doc"] in content_set:
                continue
            content_set.add(result["content"])
            doc_list.append(
                Document(
                    page_content=result["doc"],
                    metadata={
                        "source": result["source"],
                        "retrieval_content": result["content"],
                        "retrieval_data": result["data"],
                        "retrieval_score": result["score"],
                        # set common score for llm.
                        "score": result["score"],
                    },
                )
            )
        if self.enable_debug:
            debug_info[f"qd-bm25-recall-{self.index}-{self.lang}"] = (
                remove_redundancy_debug_info(opensearch_bm25_results)
            )
        return doc_list


def index_results_format(docs: list, threshold=-1):
    results = []
    for doc in docs:
        if doc.metadata["score"] < threshold:
            continue
        results.append(
            {
                "score": doc.metadata["score"],
                "source": doc.metadata["source"],
                "answer": doc.metadata["answer"],
                "question": doc.metadata["question"],
            }
        )
    # output = {"answer": json.dumps(results, ensure_ascii=False), "sources": [], "contexts": []}
    output = {
        "answer": results,
        "sources": [],
        "contexts": [],
        "context_docs": [],
        "context_sources": [],
    }
    return output
