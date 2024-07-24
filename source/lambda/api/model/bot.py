# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

import time
import uuid
from typing import Literal

from pydantic import BaseModel, Field, ConfigDict


def bot_id_generator():
    return str(uuid.uuid4())[:8]


# https://github.com/pydantic/pydantic/discussions/7121
class EmbeddingModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    type: str
    model_id: str


class RetrieverConfig(BaseModel):
    top_k: int = 3
    vector_field_name: str | None = "vector_field"
    text_field_name: str | None = "text"
    source_field_name: str | None = "source"
    use_hybrid_search: bool = False


class Retriever(BaseModel):
    index: str
    embedding: EmbeddingModel
    config: RetrieverConfig


class KnowledgeBaseRetriever(Retriever):
    name: str
    description: str


class IntentionRetriever(Retriever):
    threshold: str | None = "0.4"
    type: Literal["intent", "faq"] = "intent"


class LLMModelArgs(BaseModel):
    """DynamoDB does not support float value very well"""

    temperature: str = "0.01"
    max_tokens: str = "2048"


class LLMModel(BaseModel):
    model_config = ConfigDict(protected_namespaces=())
    type: str
    model_id: str
    model_kwargs: LLMModelArgs | None = None


class Prompt(BaseModel):
    type: str
    text: str


class Tool(BaseModel):
    name: str
    profiles: list[str] | None = None  # restrict usage in profiles


class Bot(BaseModel):
    bot_id: str = Field(default_factory=bot_id_generator)
    version: Literal["TEST", "PROD"] = "TEST"  # version can only be Test or Prod
    name: str
    description: str | None
    knowledge_base_retrievers: list[KnowledgeBaseRetriever]
    intention_retrievers: list[IntentionRetriever]
    llm: LLMModel
    prompts: list[Prompt]
    tools: list[Tool]
    user_profiles: list[str] | None = None
    created_at: int = Field(default_factory=lambda: int(time.time()))
    updated_at: int | None = None
    status: Literal["ACTIVE", "INACTIVE"] = "ACTIVE"
