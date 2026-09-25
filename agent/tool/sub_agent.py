"""子 Agent 的一次性消息循环与 task 工具声明。"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from model import ModelConfig


TASK_TOOL = {
    "type": "function",
    "function": {
        "name": "task",
        "description": "将一项独立任务交给子 Agent，返回其最终结果。",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "minLength": 1,
                    "description": "完整的子任务要求；子 Agent 不读取父对话。",
                }
            },
            "required": ["task"],
            "additionalProperties": False,
        },
    },
}


def create_sub_agent(
    client: Any,
    model: ModelConfig,
) -> Callable[[str], str | None]:
    """绑定共享的客户端和模型，返回只接收 task 的工具处理器。"""

    def run(task: str) -> str | None:
        """执行一次使用独立消息列表的子任务。"""

        return agent_loop(task, client=client, model=model)

    return run


def agent_loop(task: str, *, client: Any, model: ModelConfig) -> str | None:
    """从 task 建立独立消息列表，执行完只返回最终回复。"""

    # 在运行时导入，避免工具注册表与主循环互相导入。
    from loop.agent_loop import execute_tool
    from middleware import approval_middleware
    from tool import TOOLS

    messages = [{"role": "user", "content": task}]
    sub_tools = [tool for tool in TOOLS if tool["function"]["name"] != "task"]
    for _ in range(30):
        response = client.chat.completions.create(
            model=model.model_id,
            messages=messages,
            tools=sub_tools,
            max_tokens=8000,
        )
        response_message = response.choices[0].message

        messages.append(response_message.model_dump(exclude_none=True))

        tool_calls = response_message.tool_calls or []
        if not tool_calls:
            return response_message.content

        for tool_call in tool_calls:
            if tool_call.function.name == "task":
                tool_result = json.dumps(
                    {"ok": False, "error": "UNKNOWN_TOOL", "message": "子 Agent 不能调用 task"},
                    ensure_ascii=False,
                )
            else:
                tool_result = approval_middleware(tool_call, execute_tool)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )
