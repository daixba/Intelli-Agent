# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import json
import os
import time

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.utilities.typing import LambdaContext

from utils.dao import BotDao
from utils.aos_util import AOSUtil
from model.intention import Intention

from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from model.bot import Bot
from aws_lambda_powertools.event_handler.openapi.params import Path, Query
from aws_lambda_powertools.shared.types import Annotated
from aws_lambda_powertools.event_handler.exceptions import (
    BadRequestError,
    InternalServerError,
    NotFoundError,
    ServiceError,
    UnauthorizedError,
)

region = os.environ.get("AWS_REGION")

tracer = Tracer()
logger = Logger()
app = APIGatewayRestResolver(enable_validation=True, strip_prefixes=["/v1"])
# app.enable_swagger(path="/swagger")

aos_util = AOSUtil()
bot_table_name = os.environ.get("BOT_TABLE_NAME", "")
bot_dao = BotDao(bot_table_name)


def get_bot_by_id(bot_id: str) -> Bot:
    bot = bot_dao.get_bot(bot_id)
    if not bot or bot.status != "ACTIVE":
        raise BadRequestError(f"Invalid Bot ID {bot_id}")  # HTTP 400
    return bot


@app.post("/bots/<bot_id>/intentions")
@tracer.capture_method
def create_intention(bot_id: str, intention: Intention):
    bot = get_bot_by_id(bot_id)
    index_name = bot.intention_retrievers[0].index
    emb_model_id = bot.intention_retrievers[0].embedding.model_id
    aos_util.add_doc(index_name, emb_model_id, intention)

    return {"statusCode": 200, "body": "Success!"}


@app.get("/bots/<bot_id>/intentions")
@tracer.capture_method
def list_intentions(
    bot_id: str,
    page: Annotated[int, Query(le=999)] = 1,
    size: Annotated[int, Query(le=100)] = 20,
):
    start_from = (page - 1) * size
    bot = get_bot_by_id(bot_id)
    index_name = bot.intention_retrievers[0].index

    intention_list = aos_util.list_doc(index_name, start_from, size)

    return intention_list


@app.post("/bots/<bot_id>/intentions/<intention_id>")
@tracer.capture_method
def update_intention(bot_id: str, intention_id: str, intention: Intention):
    body: dict = app.current_event.json_body

    bot = get_bot_by_id(bot_id)
    index_name = bot.intention_retrievers[0].index

    aos_util.update_doc(index_name, intention_id, intention)

    return {"statusCode": 200, "body": "Updated"}


@app.delete("/bots/<bot_id>/intentions/<intention_id>")
@tracer.capture_method
def delete_intention(bot_id: str, intention_id: str):
    body: dict = app.current_event.json_body
    bot = get_bot_by_id(bot_id)
    index_name = bot.intention_retrievers[0].index

    aos_util.delete_doc(index_name, intention_id)

    return {"statusCode": 200, "body": "Deleted"}


@app.post(
    "/bots",
    summary="Create a Bot",
    description="Create a bot object",
    response_description="Bot ID",
)
def create_bot(bot: Bot) -> dict:
    bot_id = bot_dao.put_bot(bot)
    return {"bot_id": bot_id}


@app.get(
    "/bots/<bot_id>",
    summary="Get a Bot",
    description="Get a bot information identified by the `bot_id`.",
    response_description="The Bot object",
)
@tracer.capture_method
def get_bot(bot_id: str) -> Bot:
    bot = get_bot_by_id(bot_id)
    return bot


@app.delete(
    "/bots/<bot_id>",
    summary="Delete a Bot (soft delete)",
    description="Mark a bot as INACTIVE status",
    response_description="The Deleted Bot ID",
)
@tracer.capture_method
def delete_bot(bot_id: str) -> dict:
    bot = get_bot_by_id(bot_id)
    bot.status = "INACTIVE"
    bot.updated_at = int(time.time())
    bot_dao.put_bot(bot)
    return {"bot_id": bot.bot_id}


@app.post(
    "/bots/<bot_id>",
    summary="Update a Bot",
    description="Update a bot",
    response_description="The updated Bot ID",
)
@tracer.capture_method
def update_bot(bot_id: str, bot: Bot) -> dict:
    cur_bot = get_bot_by_id(bot_id)
    bot.bot_id = bot_id
    bot.updated_at = int(time.time())
    bot.created_at = cur_bot.created_at
    bot_dao.put_bot(bot)
    return {"bot_id": bot.bot_id}


@app.post(
    "/bots/<bot_id>/deployment",
    summary="Deploy a Bot",
    description="Create a production deployment",
    response_description="The Bot ID",
)
@tracer.capture_method
def deploy_bot(bot_id: str) -> dict:
    # Get test version first
    bot = get_bot_by_id(bot_id)
    bot.version = "PROD"  # a snapshot
    bot.updated_at = int(time.time())  # still an update
    bot_dao.put_bot(bot)
    return {"bot_id": bot.bot_id}


@app.get(
    "/bots",
    summary="List active bots",
    description="List bot object with status ACTIVE",
    response_description="A list of bot objects",
)
@tracer.capture_method
def list_bots(
    page: Annotated[int, Query(le=999)] = 1, size: Annotated[int, Query(le=100)] = 20
) -> list[Bot]:
    bots = bot_dao.list_bots(page, size)
    return bots


@logger.inject_lambda_context(correlation_id_path=correlation_paths.API_GATEWAY_REST)
@tracer.capture_lambda_handler
def lambda_handler(event: dict, context: LambdaContext):
    logger.info(json.dumps(event, indent=2))
    return app.resolve(event, context)


if __name__ == "__main__":
    print(
        app.get_openapi_json_schema(
            title="AI Customer Service API",
            version="v0.1.0",
            summary="Rest APIs for AI Customer Service Solution",
            description="This API implements all the CRUD operations related to AI Customer Service.",
        ),
    )
