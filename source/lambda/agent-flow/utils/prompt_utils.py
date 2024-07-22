from common_logic.common_utils.constant import ConstantBase


class PromptType(ConstantBase):
    RAG = "RAG"
    CONV_SUMMARY = "CONV_SUMMARY"
    GENERAL = "GENERAL"


def get_system_prompt(state: dict, prompt_type: PromptType = PromptType.GENERAL) -> str:
    user_profile = state["user_profile"]
    prompts = state["chatbot_config"]["prompts"]
    system_prompt = None
    for prompt in prompts:
        if prompt["type"] == prompt_type:
            system_prompt = prompt["text"].replace("{{user_profile}}", user_profile)
    return system_prompt
