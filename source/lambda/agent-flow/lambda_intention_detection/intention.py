from common_logic.common_utils.logger_utils import get_logger
from common_logic.common_utils.lambda_invoke_utils import chatbot_lambda_call_wrapper, invoke_lambda
import json
import pathlib

logger = get_logger("intention")


@chatbot_lambda_call_wrapper
def lambda_handler(state: dict, context=None):
    query_key = "query"
    event_body = {
        "query": state[query_key],
        "type": "qq",
        "retrievers": state['chatbot_config'].get("intention_retrievers", [])
    }
    # call retriver
    res: list[dict] = invoke_lambda(
        lambda_name='Online_Function_Retriever',
        lambda_module_path="lambda_retriever.retriever",
        handler_name='lambda_handler',
        event_body=event_body
    )

    # if not res['result']['docs']:
    #     # add default intention
    #     current_path = pathlib.Path(__file__).parent.resolve()
    #     try:
    #         with open(f'{current_path}/intention_utils/default_intent.jsonl', 'r') as json_file:
    #             json_list = list(json_file)
    #     except FileNotFoundError:
    #         logger.error(f"File note found: {current_path}/intention_utils/default_intent.jsonl")
    #         json_list = []
    #
    #     intention_fewshot_examples = []
    #     for json_str in json_list:
    #         try:
    #             intent_result = json.loads(json_str)
    #         except json.JSONDecodeError as e:
    #             logger.error(f"Error decoding JSON: {e}")
    #             intent_result = {}
    #         question = intent_result.get("question", "你好")
    #         answer = intent_result.get("answer", {})
    #         intention_fewshot_examples.append({
    #             "query": question,
    #             "score": 'n/a',
    #             "name": answer.get('intent', 'chat'),
    #             "intent": answer.get('intent', 'chat'),
    #             "kwargs": answer.get('kwargs', {}),
    #         })
    #
    #
    # else:

    intention_fewshot_examples = [{
        "query": doc['page_content'],
        "score": doc['score'],
        "name": doc['answer']['jsonlAnswer']['intent'],
        "intent": doc['answer']['jsonlAnswer']['intent'],
        "kwargs": doc['answer']['jsonlAnswer'].get('kwargs', {}),
    } for doc in res['result']['docs'] if doc['score'] > 0.4
    ]

    return intention_fewshot_examples
