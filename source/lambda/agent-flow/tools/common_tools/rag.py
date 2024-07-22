from common_logic.common_utils.lambda_invoke_utils import invoke_lambda
from common_logic.common_utils.prompt_utils import get_prompt_templates_from_ddb
from common_logic.common_utils.constant import (
    LLMTaskType
)
from common_logic.common_utils.lambda_invoke_utils import send_trace


def lambda_handler(event_body, context=None):
    state = event_body['state']

    context_list = []
    # add qq match results
    # context_list.extend(state['qq_match_results'])
    figure_list = []
    # retriever_params = state["chatbot_config"]["private_knowledge_config"]["retriever_config"]
    # retriever_params["query"] = state["query"]
    # output: str = invoke_lambda(
    #     event_body=retriever_params,
    #     lambda_name="Online_Functions",
    #     lambda_module_path="functions.functions_utils.retriever.retriever",
    #     handler_name="lambda_handler",
    # )
    query_key = "query"
    retriever_params = {
        "query": query_key,
        # **intention_config
        "type": "qd",
        "intention_retrievers": state["chatbot_config"].get("knowledge_base_retrievers", [])
    }
    # retriever_params = event_body['tool_init_kwargs']
    output: str = invoke_lambda(
        event_body=retriever_params,
        lambda_name="Online_Functions",
        lambda_module_path="lambda_retriever.retriever",
        handler_name="lambda_handler",
    )
    print(output)

    for doc in output["result"]["docs"]:
        context_list.append(doc["page_content"])
        # figure_list = figure_list + doc["figure"]

    # Remove duplicate figures
    unique_set = {tuple(d.items()) for d in figure_list}
    unique_figure_list = [dict(t) for t in unique_set]
    state['extra_response']['figures'] = unique_figure_list

    send_trace(f"\n\n**rag-contexts:** {context_list}", enable_trace=state["enable_trace"])

    llm_config = state["chatbot_config"]["llm"]
    task_type = LLMTaskType.RAG
    rag_event_body = {
        "llm_config": {
            **llm_config,
            "stream": state["stream"],
            "intent_type": LLMTaskType.RAG,
        },
        "llm_input": {
            "contexts": context_list,
            "query": state["query"],
            "chat_history": state["chat_history"],
        },
    }
    prompts = state["chatbot_config"]["prompts"]
    for prompt in prompts:
        if prompt["type"] == "RAG":
            rag_event_body["llm_config"]["system_prompt"] = prompt["text"]
            
    output: str = invoke_lambda(
        lambda_name="Online_LLM_Generate",
        lambda_module_path="lambda_llm_generate.llm_generate",
        handler_name="lambda_handler",
        event_body=rag_event_body,
    )

    return {"code": 0, "result": output}
