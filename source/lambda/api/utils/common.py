from aws_lambda_powertools import Logger
from utils.ddb_util import get_table_item

logger = Logger()

def get_index(bot_id: str, version: str):
    item = get_table_item(id=bot_id, version=version)
    intention_retrievers = item.get("intention_retrievers")
    logger.info("intention_retrievers")
    logger.info(intention_retrievers)
    index = intention_retrievers[0].get("index")
    return index

def get_index_and_model_id(bot_id: str, version: str):
    item = get_table_item(id=bot_id, version=version)
    intention_retrievers = item.get("intention_retrievers")
    logger.info("intention_retrievers")
    logger.info(intention_retrievers)

    index = intention_retrievers[0].get("index")

    embedding = intention_retrievers[0].get("embedding")
    model_id = embedding.get("model_id")

    return index, model_id

def paginate_list(input_list, page, size):
    start_index = (page - 1) * size
    end_index = start_index + size
    return input_list[start_index:end_index]