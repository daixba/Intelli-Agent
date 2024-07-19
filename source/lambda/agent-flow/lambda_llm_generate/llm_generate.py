from common_logic.common_utils.logger_utils import get_logger
from lambda_llm_generate.utils import LLMChain
from common_logic.common_utils.lambda_invoke_utils import chatbot_lambda_call_wrapper

logger = get_logger("llm_generate")


@chatbot_lambda_call_wrapper
def lambda_handler(event_body, context=None):
    print(">>>" * 10)
    print()
    llm_chain_config = event_body['llm_config']
    llm_chain_inputs = event_body['llm_input']

    print(llm_chain_config)
    chain = LLMChain.get_chain(
        **llm_chain_config
    )
    output = chain.invoke(llm_chain_inputs)

    return output
