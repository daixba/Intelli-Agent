import json
from typing import Annotated, Any, TypedDict

from common_logic.common_utils.constant import LLMTaskType, ChatbotMode, MessageType
from common_logic.common_utils.exceptions import (
    ToolNotExistError,
    ToolParameterNotExistError,
    MultipleToolNameError,
    ToolNotFound
)
from common_logic.common_utils.lambda_invoke_utils import (
    invoke_lambda,
    is_running_local,
    node_monitor_wrapper,
    send_trace,
)
from common_logic.common_utils.python_utils import add_messages, update_nest_dict
from common_logic.common_utils.logger_utils import get_logger
from common_logic.common_utils.serialization_utils import JSONEncoder
from utils.tool_calling_parse import parse_tool_calling as _parse_tool_calling
from utils.tool_execute_result_format import format_tool_call_results
from utils.tools import Tool, get_tool_by_name, tool_manager
from langgraph.graph import END, StateGraph

logger = get_logger('common_executor')


class ChatbotState(TypedDict):
    chatbot_config: dict  # chatbot config
    query: str
    ws_connection_id: str
    stream: bool
    query_rewrite: str = None  # query rewrite ret
    intent_type: str = None  # intent
    intention_fewshot_examples: list
    trace_infos: Annotated[list[str], add_messages]
    message_id: str = None
    chat_history: Annotated[list[dict], add_messages]
    agent_chat_history: Annotated[list[dict], add_messages]
    debug_infos: Annotated[dict, update_nest_dict]
    answer: Any  # final answer
    current_monitor_infos: str
    extra_response: Annotated[dict, update_nest_dict]
    contexts: str = None
    all_index_retriever_contexts: list
    current_agent_tools_def: list[dict]
    current_agent_model_id: str
    current_agent_output: dict
    parse_tool_calling_ok: bool
    enable_trace: bool
    format_intention: str
    ########### function calling parameters ###########
    # 
    current_function_calls: list[str]
    current_tool_execute_res: dict
    current_intent_tools: list
    current_tool_calls: list
    current_tool_name: str
    valid_tool_calling_names: list[str]
    # parameters to monitor the running of agent
    agent_recursion_limit: int  # the maximum number that tool_plan_and_results_generation node can be called
    agent_recursion_validation: bool
    current_agent_recursion_num: int  #


####################
# nodes in lambdas #
####################


@node_monitor_wrapper
def query_preprocess_lambda(state: ChatbotState):
    output: str = invoke_lambda(
        event_body=state,
        lambda_name="Online_Query_Preprocess",
        lambda_module_path="lambda_query_preprocess.query_preprocess",
        handler_name="lambda_handler",
    )
    send_trace(f"\n\n**query_rewrite:** \n{output}", state["stream"], state["ws_connection_id"], state["enable_trace"])
    return {"query_rewrite": output}


@node_monitor_wrapper
def intention_detection_lambda(state: ChatbotState):
    intention_fewshot_examples = invoke_lambda(
        lambda_module_path="lambda_intention_detection.intention",
        lambda_name="Online_Intention_Detection",
        handler_name="lambda_handler",
        event_body=state,
    )

    # send trace
    send_trace(
        f"**intention retrieved:**\n{json.dumps(intention_fewshot_examples, ensure_ascii=False, indent=2)}",
        state["stream"], state["ws_connection_id"], state["enable_trace"])
    current_intent_tools: list[str] = list(
        set([e["intent"] for e in intention_fewshot_examples])
    )
    return {
        "intention_fewshot_examples": intention_fewshot_examples,
        "current_intent_tools": current_intent_tools,
        "intent_type": "intention detected",
    }


@node_monitor_wrapper
def rag_all_index_lambda(state: ChatbotState):
    # call retrivever
    query_key = "query"
    event_body = {
        "query": state[query_key],
        # **intention_config
        "type": "qd",
        "intention_retrievers": state['chatbot_config'].get("knowledge_base_retrievers", [])
    }
    output: str = invoke_lambda(
        event_body=event_body,
        lambda_name="Online_Function_Retriever",
        lambda_module_path="lambda_retriever.retriever",
        handler_name="lambda_handler",
    )
    contexts = [doc["page_content"] for doc in output["result"]["docs"]]
    return {"contexts": contexts}


@node_monitor_wrapper
def rag_llm_lambda(state: ChatbotState):
    llm_config = state["chatbot_config"]["llm"]
    event_body = {
        "llm_config": {
            **llm_config,
            "stream": state["stream"],
            "intent_type": LLMTaskType.RAG,
        },
        "llm_input": {
            "contexts": [state["contexts"]],
            "query": state["query"],
            "chat_history": state["chat_history"],
        },
    }
    prompts = state["chatbot_config"]["prompts"]
    for prompt in prompts:
        if prompt["type"] == "RAG":
            event_body["llm_config"]["system_prompt"] = prompt["text"]

    output: str = invoke_lambda(
        lambda_name="Online_LLM_Generate",
        lambda_module_path="lambda_llm_generate.llm_generate",
        handler_name="lambda_handler",
        event_body=event_body,
    )
    return {"answer": output}


@node_monitor_wrapper
def agent_lambda(state: ChatbotState):
    current_agent_output: dict = invoke_lambda(
        event_body=state,
        lambda_name="Online_Agent",
        lambda_module_path="lambda_agent.agent",
        handler_name="lambda_handler",

    )
    current_agent_recursion_num = state['current_agent_recursion_num'] + 1
    send_trace(
        f"\n\n**current_agent_output:** \n{json.dumps(current_agent_output['agent_output'], ensure_ascii=False, indent=2)}\n\n **current_agent_recursion_num:** {current_agent_recursion_num}",
        state["stream"], state["ws_connection_id"])
    return {
        "current_agent_output": current_agent_output,
        "current_agent_recursion_num": current_agent_recursion_num
    }


@node_monitor_wrapper
def parse_tool_calling(state: ChatbotState):
    """executor lambda
    Args:
        state (NestUpdateState): _description_

    Returns:
        _type_: _description_
    """
    # parse tool_calls:
    try:
        output = _parse_tool_calling(
            agent_output=state['current_agent_output']
        )
        tool_calls = output['tool_calls']
        send_trace(f"\n\n**tool_calls parsed:** \n{tool_calls}", state["stream"], state["ws_connection_id"],
                   state["enable_trace"])
        if not state["extra_response"].get("current_agent_intent_type", None):
            state["extra_response"]["current_agent_intent_type"] = output['tool_calls'][0]["name"]

        return {
            "parse_tool_calling_ok": True,
            "current_tool_calls": tool_calls,
            "agent_chat_history": [output['agent_message']]
        }

    except (ToolNotExistError,
            ToolParameterNotExistError,
            MultipleToolNameError,
            ToolNotFound
            ) as e:
        send_trace(f"\n\n**tool_calls parse failed:** \n{str(e)}", state["stream"], state["ws_connection_id"],
                   state["enable_trace"])
        return {
            "parse_tool_calling_ok": False,
            "agent_chat_history": [
                e.agent_message,
                e.error_message
            ]
        }


@node_monitor_wrapper
def agent(state: ChatbotState):
    response = app_agent.invoke(state)
    return response


@node_monitor_wrapper
def tool_execute_lambda(state: ChatbotState):
    """executor lambda
    Args:
        state (NestUpdateState): _description_

    Returns:
        _type_: _description_
    """
    tool_calls = state['current_tool_calls']
    assert len(tool_calls) == 1, tool_calls
    tool_call_results = []
    for tool_call in tool_calls:
        tool_name = tool_call["name"]
        tool_kwargs = tool_call['kwargs']
        # call tool
        output = invoke_lambda(
            event_body={
                "tool_name": tool_name,
                "state": state,
                "kwargs": tool_kwargs
            },
            lambda_name="Online_Tool_Execute",
            lambda_module_path="utils.lambda_tool",
            handler_name="lambda_handler"
        )
        tool_call_results.append({
            "name": tool_name,
            "output": output,
            "kwargs": tool_call['kwargs'],
            "model_id": tool_call['model_id']
        })

    output = format_tool_call_results(tool_calls[0]['model_id'], tool_call_results)
    send_trace(f'**tool_execute_res:** \n{output["tool_message"]["content"]}')
    return {"agent_chat_history": [output['tool_message']]}


def format_reply(state: ChatbotState):
    recent_tool_name = state["current_tool_calls"][0]['name']
    if recent_tool_name == 'comfort':
        return {"answer": "不好意思没能帮到您，是否帮你转人工客服？"}
    if recent_tool_name == 'transfer':
        return {"answer": "立即为您转人工客服，请稍后"}


def give_rhetorical_question(state: ChatbotState):
    recent_tool_calling: list[dict] = state["current_tool_calls"][0]
    return {"answer": recent_tool_calling["kwargs"]["question"]}


def give_final_response(state: ChatbotState):
    recent_tool_calling: list[dict] = state["current_tool_calls"][0]
    # give_rhetorical_question
    if "question" in recent_tool_calling["kwargs"].keys():
        answer = recent_tool_calling["kwargs"]["question"]
    elif "response" in recent_tool_calling["kwargs"].keys():
        answer = recent_tool_calling["kwargs"]["response"]
    elif "abbr" in recent_tool_calling["kwargs"].keys():
        answer = recent_tool_calling["kwargs"]["abbr"]
    else:
        answer = format_reply(state)["answer"]
    return {"answer": answer}


def qq_matched_reply(state: ChatbotState):
    return {"answer": state["answer"]}


################
# define edges #
################

def query_route(state: dict):
    # return f"{state['chatbot_config']['chatbot_mode']} mode"
    return "agent mode"


def intent_route(state: dict):
    if not state['intention_fewshot_examples']:
        state['extra_response']['current_agent_intent_type'] = 'final_rag'
        return 'no clear intention'
    return state["intent_type"]


# def agent_route(state: dict):
#     if state["agent_state"] == "tool calling":
#         return "tool calling"
#     else:
#         return "no need tool calling"

def agent_route(state: dict):
    state["agent_recursion_validation"] = state['current_agent_recursion_num'] < state['agent_recursion_limit']
    if state["parse_tool_calling_ok"]:
        state["current_tool_name"] = state["current_tool_calls"][0]["name"]
    else:
        state["current_tool_name"] = ""

    # if state["agent_recursion_validation"] and not state["parse_tool_calling_ok"]:
    #     return "invalid tool calling"
    if state["agent_recursion_validation"]:
        if state["current_tool_name"] in ["QA", "service_availability", "explain_abbr"]:
            return "force to retrieve all knowledge"
        elif state["current_tool_name"] in state["valid_tool_calling_names"]:
            return "valid tool calling"
        else:
            return "no need tool calling"
    else:
        return "force to retrieve all knowledge"


def rag_all_index_lambda_route(state: dict):
    # TODO: Check this.
    # if state['chatbot_config']['chatbot_mode'] == ChatbotMode.rag_mode:
    #     return "generate results in rag mode"

    # if not state.get('intention_fewshot_examples', []) and state['current_agent_recursion_num'] == 0:
    # if state['current_agent_recursion_num'] == 0:
    #     return "no clear intention"
    # else:
    return "generate results in rag mode"


#############################
# define online top-level graph #
#############################

def build_graph():
    workflow = StateGraph(ChatbotState)
    # add all nodes
    workflow.add_node("query_preprocess", query_preprocess_lambda)
    # rag mode
    workflow.add_node("all_knowledge_retrieve", rag_all_index_lambda)
    workflow.add_node("llm_rag_results_generation", rag_llm_lambda)
    # agent mode
    workflow.add_node("intention_detection", intention_detection_lambda)
    workflow.add_node("matched_query_return", qq_matched_reply)
    workflow.add_node("agent", agent)
    workflow.add_node("tools_execution", tool_execute_lambda)
    workflow.add_node("final_results_preparation", give_final_response)

    # add all edges
    workflow.set_entry_point("query_preprocess")
    workflow.add_edge("llm_rag_results_generation", END)
    # agent mode
    # workflow.add_edge("tools_choose_and_results_generation", "results_evaluation")
    workflow.add_edge("tools_execution", "agent")
    workflow.add_edge("matched_query_return", "final_results_preparation")
    workflow.add_edge("final_results_preparation", END)

    # add conditional edges
    # choose running mode based on user selection:
    # 1. chat mode: let llm generate results directly
    # 2. rag mode: retrive all knowledge and let llm generate results
    # 3. agent mode: let llm generate results based on intention detection, tool calling and retrieved knowledge
    # workflow.add_conditional_edges(
    #     "query_preprocess",
    #     query_route,
    #     {
    #         "chat mode": "llm_direct_results_generation",
    #         "rag mode": "all_knowledge_retrieve",
    #         "agent mode": "intention_detection",
    #     },
    # )
    workflow.add_edge("query_preprocess", "intention_detection")

    # three running branch will be chosen based on intention detection results:
    # 1. query matched: if very similar queries were found in knowledge base, these queries will be given as results
    # 2. no clear intentions: if no clear intention detected, all knowledge will be retrieved and let llm give the answer based on retrieved results (rag mode)
    # 3. intention detected: if intention detected, the agent logic will be invoked
    workflow.add_conditional_edges(
        "intention_detection",
        intent_route,
        {
            "similar query found": "matched_query_return",
            "intention detected": "agent",
            "no clear intention": "all_knowledge_retrieve",
        },
    )

    # the results of agent planning will be evaluated and decide next step:
    # 1. invalid tool calling: if agent makes clear mistakes, like wrong tool names or format, it will be forced to plan again
    # 2. valid tool calling: the agent chooses the valid tools
    # 3. generate results: based on running of tools, agent thinks it's ok to generate results.
    # 4. force retrieve all knowledge and generate results: to address hallucination and stability issues, we force agent to retrieve all knowledge and generate results:
    # 4.1 the agent believes that it can produce results without executing tools
    # 4.2 the tools_choose_and_results_generation node reaches its maximum recusion limit
    workflow.add_conditional_edges(
        "agent",
        agent_route,
        {
            # "invalid tool calling": "tools_choose_and_results_generation",
            "valid tool calling": "tools_execution",
            "no need tool calling": "final_results_preparation",
            "force to retrieve all knowledge": "all_knowledge_retrieve",
        },
    )

    # when all knowledge retrieved, there are two possible next steps:
    # 1. no clear intention: this happens when no clear intention (no few shots) is detected, we give agent enough context to think and plan.
    # 2. generate results in rag mode: let llm generate results based on retrieved knowledge, this happens in the following scenarios:
    # 2.1 in rag mode based on user selection at beginning
    # 2.2 agent thinks it needs to retrieve all the knowledge to generate the results
    # 2.3 the agent believes that it can produce results without executing tools
    # 2.4 the tools_choose_and_results_generation node reaches its maximum recusion limit
    workflow.add_conditional_edges(
        "all_knowledge_retrieve",
        rag_all_index_lambda_route,
        {
            "no clear intention": "agent",
            "generate results in rag mode": "llm_rag_results_generation",
        },
    )
    app = workflow.compile()
    return app


#############################
# define online agent graph #
#############################

def build_agent_graph():
    def _results_evaluation_route(state: dict):
        # TODO: pass no need tool calling or valid tool calling?
        state["agent_recursion_validation"] = state['current_agent_recursion_num'] < state['agent_recursion_limit']
        if state["agent_recursion_validation"] and not state["parse_tool_calling_ok"]:
            return "invalid tool calling"
        return "continue"

    workflow = StateGraph(ChatbotState)
    workflow.add_node("tools_choose_and_results_generation", agent_lambda)
    workflow.add_node("results_evaluation", parse_tool_calling)

    # edge
    workflow.set_entry_point("tools_choose_and_results_generation")
    workflow.add_edge("tools_choose_and_results_generation", "results_evaluation")
    workflow.add_conditional_edges(
        "results_evaluation",
        _results_evaluation_route,
        {
            "invalid tool calling": "tools_choose_and_results_generation",
            "continue": END,
            # "no need tool calling": "final_results_preparation",
        }
    )
    app = workflow.compile()
    return app


app = None
app_agent = None


def run(event_body):
    """
    Entry point for the Lambda function.
    :param event_body: The event body for lambda function.
    return: answer(str)
    """
    global app, app_agent
    if app is None:
        app = build_graph()

    if app_agent is None:
        app_agent = build_agent_graph()

    # debuging
    # TODO only write when run local
    if is_running_local():
        with open("common_entry_workflow.png", "wb") as f:
            f.write(app.get_graph().draw_png())

        with open("common_entry_agent_workflow.png", "wb") as f:
            f.write(app_agent.get_graph().draw_png())

    ################################################################################
    # prepare inputs and invoke graph
    logger.info(f'event_body:\n{json.dumps(event_body, ensure_ascii=False, indent=2, cls=JSONEncoder)}')

    chatbot_config = event_body["chatbot_config"]
    query = event_body["query"]
    use_history = event_body.get("use_history", "true").lower() == "true"
    chat_history = event_body["chat_history"] if use_history else []
    stream = event_body["stream"]
    message_id = event_body["custom_message_id"]
    ws_connection_id = event_body["ws_connection_id"]
    enable_trace = event_body.get("enable_trace", "true").lower() == "true"
    # get all registered tools with parameters
    valid_tool_calling_names = tool_manager.get_names_from_tools_with_parameters()

    # invoke graph and get results
    response = app.invoke(
        {
            "stream": stream,
            "chatbot_config": chatbot_config,
            "query": query,
            "enable_trace": enable_trace,
            "trace_infos": [],
            "message_id": message_id,
            "chat_history": chat_history,
            "agent_chat_history": [],
            "ws_connection_id": ws_connection_id,
            "debug_infos": {},
            "extra_response": {},
            "agent_recursion_limit": 5,  # chatbot_config['agent_recursion_limit'],
            "current_agent_recursion_num": 0,
            "valid_tool_calling_names": valid_tool_calling_names
        }
    )

    return {"answer": response["answer"], **response["extra_response"]}


if __name__ == '__main__':
    event_body = {
        "query": "Hello",
        "entry_type": "common",
        "session_id": "cfa48a53-5e6a-4942-a900-639b1b48d7da",
        "use_history": True,
        "enable_trace": True,
        "use_websearch": True,
        "chatbot_config": {
            {
                "bot_id": "a1b2",
                "version": "TEST",
                "description": "Test Bot",
                "knowledge_base_retrievers": [
                    {
                        "index": "test-qa",
                        "config": {
                            "top_k": "3",
                            "vector_field_name": "sentence_vector",
                            "text_field_name": "paragraph",
                            "source_field_name": "source",
                            "use_hybrid_search": "true",
                        },
                        "embedding": {
                            "type": "Bedrock",
                            "model_id": "amazon.titan-embed-text-v2:0"
                        }
                    }
                ],
                "intention_retrievers": [
                    {
                        "index": "test-intent",
                        "config": {
                            "top_k": "3"
                        },
                        "embedding": {
                            "type": "Bedrock",
                            "model_id": "cohere.embed-english-v3"
                        }
                    }
                ],
                "llm": {
                    "type": "Bedrock",
                    "model_id": "anthropic.claude-3-sonnet-20240229-v1:0",
                    "model_kwargs": {
                        "temperature": 0.0,
                        "max_tokens": 4096
                    }
                },
                "prompts": [
                    {
                        "name": "RAG",
                        "text": "You are a customer service chatbot. You ALWAYS follow these guidelines when writing your response to user's query:\n<guidelines>\n- NERVER say \"\u6839\u636e\u641c\u7d22\u7ed3\u679c/\u5927\u5bb6\u597d/\u8c22\u8c22...\".\n</guidelines>\n\nHere are some documents for you to reference for your query.\n<docs>\n{context}\n</docs>"},
                    {
                        "name": "GENERAL",
                        "text": "You are a customer service chatbot."
                    },
                    {
                        "name": "CONV_SUMMARY",
                        "text": "Given the following conversation between `USER` and `AI`, and a follow up `USER` reply, Put yourself in the shoes of `USER`, rephrase the follow up `USER` reply to be a standalone reply.\n\nChat History:\n{history}\n\nThe USER's follow up reply: {question}"
                    }
                ],
                "tools": [
                    {
                        "name": "get_weather"
                    }
                ]
            }
        },
        "user_id": "b85163d0-6011-70fd-216e-d1d6d64f153d"
    }
    run(event_body)
