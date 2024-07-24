# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import boto3
from aws_lambda_powertools import Logger

from model.bot import Bot
from boto3.dynamodb.conditions import Key, Attr

logger = Logger("DAO")


class BotDao:
    def __init__(self, table_name) -> None:
        ddb = boto3.resource("dynamodb")
        self._table = ddb.Table(table_name)
        self._version = "TEST"

    def put_bot(self, bot: Bot) -> str:
        """Can be used for create or update"""
        self._table.put_item(Item=bot.model_dump())
        return bot.bot_id

    def get_bot(self, bot_id: str) -> Bot | None:
        response = self._table.get_item(
            Key={"bot_id": bot_id, "version": self._version}
        )

        if "Item" in response:
            item = response["Item"]
            bot = Bot(**item)
            return bot
        return None

    def list_bots(self, page: int = 1, size: int = 20) -> list[Bot]:
        # query by GSI: byVersion
        response = self._table.query(
            IndexName="byVersion",
            KeyConditionExpression=Key("version").eq(self._version),
            ScanIndexForward=False,  # descending order by created_at,
            FilterExpression=Attr("status").eq("ACTIVE"),
        )
        items = response["Items"]
        count = len(items)
        logger.info("Totally %s bots found", count)
        start = (page - 1) * size
        end = start + size
        if start > count:
            # reset start and end
            start = 0
            end = size

        return [Bot(**item) for item in items[start:end]]
