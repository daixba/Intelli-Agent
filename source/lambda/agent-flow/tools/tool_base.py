from langchain.pydantic_v1 import BaseModel, Field
from enum import Enum
from typing import Union, Callable
from common_logic.common_utils.constant import SceneType, ToolRuningMode
from tools.common_tools import (
    give_rhetorical_question,
    give_final_response,
    chat,
    knowledge_base_retrieve,
    rag
)

from tools.custom_tools import get_weather


class ToolDefType(Enum):
    openai = "openai"


class Tool(BaseModel):
    name: str = Field(description="tool name")
    lambda_name: str = Field(description="lambda name")
    lambda_module_path: Union[str, Callable] = Field(description="local module path")
    handler_name: str = Field(description="local handler name", default="lambda_handler")
    tool_def: dict = Field(description="tool definition")
    tool_init_kwargs: dict = Field(description="tool initial kwargs", default=None)
    running_mode: str = Field(description="tool running mode, can be loop or output", default=ToolRuningMode.LOOP)
    tool_def_type: ToolDefType = Field(description="tool definition type", default=ToolDefType.openai.value)
    scene: str = Field(description="tool use scene", default=SceneType.COMMON)
    # should_ask_parameter: bool = Field(description="tool use scene")


class ToolManager:
    def __init__(self) -> None:
        self.tools = {}

    def get_tool_id(self, tool_name: str, scene: str):
        return f"{tool_name}__{scene}"

    def register_tool(self, tool_info: dict):
        tool_def = tool_info['tool_def']
        if "parameters" not in tool_def:
            tool_def['parameters'] = {
                "type": "object",
                "properties": {},
                "required": []
            }

        tool = Tool(**tool_info)
        assert tool.tool_def_type == ToolDefType.openai.value, f"tool_def_type: {tool.tool_def_type} not support"
        self.tools[self.get_tool_id(tool.name, tool.scene)] = tool

    def register_rag_tool(self, name: str, description: str):
        self.register_tool({
            "name": name,
            "scene": SCENE,
            "lambda_name": LAMBDA_NAME,
            "lambda_module_path": rag.lambda_handler,
            "tool_def": {
                "name": "QA",
                "description": description,
            },
            "running_mode": ToolRuningMode.ONCE
        })

    def get_tool_by_name(self, name, scene=SceneType.COMMON):
        return self.tools[self.get_tool_id(name, scene)]


tool_manager = ToolManager()
get_tool_by_name = tool_manager.get_tool_by_name

SCENE = SceneType.COMMON
LAMBDA_NAME = "lambda_common_tools"

tool_manager.register_tool({
    "name": "get_weather",
    "scene": SCENE,
    "lambda_name": LAMBDA_NAME,
    "lambda_module_path": get_weather.lambda_handler,
    "tool_def": {
        "name": "get_weather",
        "description": "Get the current weather for `city_name`",
        "parameters": {
            "type": "object",
            "properties": {
                "city_name": {
                    "description": "The name of the city to be queried",
                    "type": "string"
                },
            },
            "required": ["city_name"]
        }
    },
    "running_mode": ToolRuningMode.ONCE
}
)

tool_manager.register_tool(
    {
        "name": "give_rhetorical_question",
        "scene": SCENE,
        "lambda_name": LAMBDA_NAME,
        "lambda_module_path": give_rhetorical_question.lambda_handler,
        "tool_def": {
            "name": "give_rhetorical_question",
            "description": "If the user's question is not clear and specific, resulting in the inability to call other tools, please call this tool to ask the user a rhetorical question",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "description": "The rhetorical question to user",
                        "type": "string"
                    },
                },
                "required": ["question"],
            },
        },
        "running_mode": ToolRuningMode.ONCE
    }
)

tool_manager.register_tool(
    {
        "name": "give_final_response",
        "scene": SCENE,
        "lambda_name": LAMBDA_NAME,
        "lambda_module_path": give_final_response.lambda_handler,
        "tool_def": {
            "name": "give_final_response",
            "description": "If none of the other tools need to be called, call the current tool to complete the direct response to the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "response": {
                        "description": "Response to user",
                        "type": "string"
                    }
                },
                "required": ["response"]
            },
        },
        "running_mode": ToolRuningMode.ONCE
    }
)

tool_manager.register_tool({
    "name": "chat",
    "scene": SCENE,
    "lambda_name": LAMBDA_NAME,
    "lambda_module_path": chat.lambda_handler,
    "tool_def": {
        "name": "chat",
        "description": "casual talk with AI",
        "parameters": {
            "type": "object",
            "properties": {
                "response": {
                    "description": "response to users",
                    "type": "string"
                }},
            "required": ["response"]
        },
    },
    "running_mode": ToolRuningMode.ONCE
})

tool_manager.register_tool({
    "name": "knowledge_base_retrieve",
    "scene": SCENE,
    "lambda_name": LAMBDA_NAME,
    "lambda_module_path": knowledge_base_retrieve.lambda_handler,
    "tool_def": {
        "name": "knowledge_base_retrieve",
        "description": "retrieve domain knowledge",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "description": "query for retrieve",
                    "type": "string"
                }},
            "required": ["query"]
        },
    },
    "running_mode": ToolRuningMode.LOOP
})

# tool_manager.register_tool({
#     "name": "QA",
#     "scene": SCENE,
#     "lambda_name": LAMBDA_NAME,
#     "lambda_module_path": rag.lambda_handler,
#     "tool_def": {
#         "name": "QA",
#         "description": "answer question according to searched relevant content",
#     },
#     "running_mode": ToolRuningMode.ONCE
# })


tool_manager.register_tool({
    "name": "comfort",
    "scene": SCENE,
    "lambda_name": LAMBDA_NAME,
    "lambda_module_path": chat.lambda_handler,
    "tool_def": {
        "name": "comfort",
        "description": "comfort user to mitigate their bad emotion",
        "parameters": {
            "type": "object",
            "properties": {
                "response": {
                    "description": "response to users",
                    "type": "string"
                }},
            "required": ["response"]
        },
    },
    "running_mode": ToolRuningMode.ONCE
})

tool_manager.register_tool({
    "name": "greeting",
    "scene": SCENE,
    "lambda_name": LAMBDA_NAME,
    "lambda_module_path": chat.lambda_handler,
    "tool_def": {
        "name": "greeting",
        "description": "Send greeting back to user and ask: How can I assist you today?",
        "parameters": {
            "type": "object",
            "properties": {
                "response": {
                    "description": "response to users",
                    "type": "string"
                }},
            "required": ["response"]
        },
    },
    "running_mode": ToolRuningMode.ONCE
})
# tool_manager.register_tool({
#     "name": "转人工",
#     "lambda_name": "",
#     "lambda_module_path": "functions.retail_tools.lambda_human",
#     "tool_def": {
#         "name": "转人工",
#         "description": "转人工",
#         # "parameters":{
#         #     "required": ["response"]
#         # },
#     },
#     "running_mode": "output"
# })
# tool_manager.register_tool({
#     "name": "信息缺失",
#     "lambda_name": "",
#     "lambda_module_path": "",
#     "tool_def": {
#         "name": "信息缺失",
#         "description": "信息缺失",
#         # "parameters":{
#         #     "required": ["response"]
#         # },
#     },
#     "running_mode": "output"
# })
