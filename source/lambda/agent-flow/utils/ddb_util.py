import os

import boto3

table_name = os.environ.get("BOT_TABLE_NAME", "")

client = boto3.resource("dynamodb")

table = client.Table(table_name)

def get_table_item(id: str, version: str):
    response = table.get_item(
        Key={
            "bot_id": id,
            "version": version
        }
    )
    item = response.get("Item")
    return item

def rest_get_bot_info(id: str, version: str):
    bot = get_table_item(id, version)
    model_kwargs = bot["llm"]["model_kwargs"]
    model_kwargs["temperature"] = float(bot["llm"].get("temperature", "0.01"))
    model_kwargs["max_tokens"] = int(bot["llm"].get("max_tokens", "4096"))

    return bot
