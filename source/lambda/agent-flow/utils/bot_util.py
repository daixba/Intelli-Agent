import os

import boto3

table_name = os.environ.get("BOT_TABLE_NAME", "")

client = boto3.resource("dynamodb")

table = client.Table(table_name)

PROD_VERSION = "PROD"

def get_table_item(id: str, version: str):
    response = table.get_item(
        Key={
            "bot_id": id,
            "version": version
        }
    )
    item = response.get("Item")
    return item

def scan_table_item():
    response = table.scan()
    bots = response['Items']
    if len(bots) == 0:
        raise RuntimeError("No bots created")
    return bots

def get_bot_info_from_table(id: str):
    bot = get_table_item(id, PROD_VERSION)
    model_kwargs = bot["llm"]["model_kwargs"]
    model_kwargs["temperature"] = float(bot["llm"].get("temperature", "0.01"))
    model_kwargs["max_tokens"] = int(bot["llm"].get("max_tokens", "4096"))

    return bot

def scan_bot_info_from_table():
    # Temporary Use
    # TODO: Update this.
    bots = scan_table_item()
    bot = bots[0]
    model_kwargs = bot["llm"]["model_kwargs"]
    model_kwargs["temperature"] = float(bot["llm"].get("temperature", "0.01"))
    model_kwargs["max_tokens"] = int(bot["llm"].get("max_tokens", "4096"))
    return bot