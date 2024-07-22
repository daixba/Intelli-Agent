from langchain.schema.runnable import (
    RunnableLambda
)

from common_logic.common_utils.logger_utils import get_logger
from common_logic.common_utils.langchain_utils import chain_logger
from common_logic.common_utils.lambda_invoke_utils import invoke_lambda, chatbot_lambda_call_wrapper
from common_logic.common_utils.constant import LLMTaskType
from tools.tool_base import get_tool_by_name
from utils.prompt_utils import get_system_prompt, PromptType

logger = get_logger("agent")


def tool_calling(state: dict):
    # print(state)
    # tools = state['intent_fewshot_tools'] + [t["name"] for t in state["chatbot_config"]['tools']]
    tools = []

    user_profile = state.get("user_profile", "")
    print(user_profile)
    for t in state["chatbot_config"]['tools']:
        profiles = t.get("profiles", [])
        if profiles and user_profile:
            if user_profile in profiles:
                tools.append(t["name"])
        else:
            tools.append(t["name"])

    tools += ["comfort", "greeting", "give_final_response", "give_rhetorical_question"]
    tool_defs = [get_tool_by_name(tool_name).tool_def for tool_name in tools]
    print(tool_defs)

    llm = state["chatbot_config"]['llm']
    llm_config = {
        **llm,
        "tools": tool_defs,
        "fewshot_examples": state['intent_fewshot_examples'],
        "system_prompt": get_system_prompt(state, PromptType.GENERAL),
    }

    agent_llm_type = state.get("agent_llm_type", None) or LLMTaskType.TOOL_CALLING

    output = invoke_lambda(
        lambda_name='Online_LLM_Generate',
        lambda_module_path="lambda_llm_generate.llm_generate",
        handler_name='lambda_handler',
        event_body={
            "llm_config": {**llm_config, "intent_type": agent_llm_type},
            "llm_input": state
        }
    )

    return {
        "agent_output": output,
        "current_agent_tools_def": tool_defs,
        "current_agent_model_id": llm['model_id']
    }


@chatbot_lambda_call_wrapper
def lambda_handler(state: dict, context=None):
    output = tool_calling(state)
    return output
