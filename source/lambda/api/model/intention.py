# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: Apache-2.0

from typing import Literal

from pydantic import (
    BaseModel
)


class Intention(BaseModel):
    question: str
    answer: str
    type: Literal["Intent", "FAQ"] = "Intent"  # Two types of intents
    kwargs: dict[str, str]
