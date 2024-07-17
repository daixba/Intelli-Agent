import os

import boto3
from aws_lambda_powertools import Logger

logger = Logger()

table_name = os.environ.get("BOT_TABLE_NAME", "")

client = boto3.resource("dynamodb")

table = client.Table(table_name)

def get_table_item(id: str, version: str):
    logger.info(f"Get bot from DynamoDB by id {id}, and version {version}")
    response = table.get_item(
        Key={
            "bot_id": id,
            "version": version
        }
    )
    item = response.get("Item")
    return item
