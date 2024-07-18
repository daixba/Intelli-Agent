# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from enum import Enum
from pydantic import (
    BaseModel
)


class CommonEnum(str, Enum):
    def __str__(self) -> str:
        return self.value

    def __repr__(self) -> str:
        return self.value

class BotVersion(CommonEnum):
    TEST = "TEST"
    PROD = "PROD"

class IntentAndKwarg(BaseModel):
    intent: str
    kwargs: dict[str, str]

class Intention(BaseModel):
    question: str
    answer: IntentAndKwarg

class Pagination(BaseModel):
    page: int
    size: int