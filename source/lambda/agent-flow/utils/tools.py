from langchain.pydantic_v1 import BaseModel, Field
from enum import Enum


class ToolDefType(Enum):
    openai = "openai"


class Tool(BaseModel):
    name: str = Field(description="tool name")
    lambda_name: str = Field(description="lambda name")
    lambda_module_path: str = Field(description="local module path")
    handler_name: str = Field(description="local handler name", default="lambda_handler")
    tool_def: dict = Field(description="tool definition")
    running_mode: str = Field(description="tool running mode, can be loop or output", default="loop")
    tool_def_type: ToolDefType = Field(description="tool definition type", default=ToolDefType.openai.value)
    should_ask_parameter: str = Field(description="whether should ask about parameters of tools", default="True")


class ToolManager:
    def __init__(self) -> None:
        self.tools = {}

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
        self.tools[tool.name] = tool

    def get_tool_by_name(self, name):
        return self.tools[name]

    def get_names_from_tools_with_parameters(self):
        valid_tool_names_with_parameters = []
        for tool_name, tool_info in self.tools.items():
            if tool_info.running_mode == 'loop':
                valid_tool_names_with_parameters.append(tool_name)
        return valid_tool_names_with_parameters


tool_manager = ToolManager()
get_tool_by_name = tool_manager.get_tool_by_name

tool_manager.register_tool({
    "name": "get_weather",
    "lambda_name": "",
    "lambda_module_path": "custom_tools.get_weather.main",
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
    "running_mode": "loop"
}
)

tool_manager.register_tool(
    {
        "name": "give_rhetorical_question",
        "lambda_name": "",
        "lambda_module_path": "functions.lambda_give_rhetorical_question.give_rhetorical_question",
        "tool_def": {
            "name": "give_rhetorical_question",
            "description": "If the user's question is not clear and specific, resulting in the inability to call other tools, please call this tool to ask the user a rhetorical question",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "description": "Rhetorical questions for users",
                        "type": "string"
                    },
                },
                "required": ["question"],
            },
        },
        "running_mode": "output"
    }
)

tool_manager.register_tool(
    {
        "name": "give_final_response",
        "lambda_name": "",
        "lambda_module_path": "",
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
        "running_mode": "output"
    }
)

# tool_manager.register_tool(
#     {
#         "name": "search_lihoyo",
#         "lambda_name": "",
#         "lambda_module_path": "lambda_retriever.retriever",
#         "tool_def": {
#             "name": "search_lihoyo",
#             "description": "Retrieve knowledge about lihoyo",
#             "parameters": {
#                 "type": "object",
#                 "properties": {
#                     "query": {
#                         "description": "query to retrieve",
#                         "type": "string"
#                     }},
#                 "required": ["query"]
#             },
#         },
#         "running_mode": "loop"
#     }
# )

tool_manager.register_tool({
    "name": "assist",
    "lambda_name": "",
    "lambda_module_path": "",
    "tool_def": {
        "name": "assist",
        "description": "assist user to do some office work",
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
    "running_mode": "output"
})

tool_manager.register_tool({
    "name": "QA",
    "lambda_name": "",
    "lambda_module_path": "lambda_retriever.retriever",
    "tool_def": {
        "name": "QA",
        "description": "answer question about aws according to searched relevant content",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "description": "query to retrieve",
                    "type": "string"
                }},
            "required": ["query"]
        },
    },
    "running_mode": "loop"
})

tool_manager.register_tool({
    "name": "chat",
    "lambda_name": "chat",
    "lambda_module_path": "function.common_tools.chat",
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
    "running_mode": "output"
})

# tool_manager.register_tool({
#     "name": "comfort",
#     "scenario": "common",
#     "lambda_name": "comfort",
#     "lambda_module_path": "functions.common_tools.comfort",
#     "tool_def": {
#         "name": "comfort",
#         "description": "comfort user to mitigate their bad emotion",
#         # "parameters": {
#         #     "type": "object",
#         #     "properties": {
#         #         "response": {
#         #             "description": "response to users",
#         #             "type": "string"
#         #     }},
#         #     "required": ["response"]
#         # },
#     },
#     "running_mode": "output"
# })

# tool_manager.register_tool({
#     "name": "transfer",
#     "lambda_name": "",
#     "lambda_module_path": "functions.common_tools.transfer",
#     "tool_def": {
#         "name": "transfer",
#         "description": "transfer the conversation to manual customer service",
#         # "parameters": {
#         #     "type": "object",
#         #     "properties": {
#         #         "response": {
#         #             "description": "response to users",
#         #             "type": "string"
#         #     }},
#         #     "required": ["response"]
#         # },
#     },
#     "running_mode": "output"
# })

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
