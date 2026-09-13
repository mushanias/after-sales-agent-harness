"""售后 Agent 的系统提示、工具执行与核心循环。"""

from __future__ import annotations

import json
from typing import Any

from hooks import trigger_hooks
from middleware import approval_middleware
from model import ModelConfig
from tool import TOOL_HANDLERS, TOOLS


SYSTEM_PROMPT = """你是售后处理 Agent。
当用户提供订单号并询问订单信息时，使用 lookup_order 查询。
只能根据工具返回的信息回答，不要编造订单或处理结果。
"""

def execute_tool(tool_call: Any) -> str:
    """
    在 Loop 允许执行工具后，解析参数并调用已注册的处理器。

    调用方式：
        execute_tool(tool_call)

    输入字段：
        tool_call：模型 SDK 返回的工具调用对象，必须包含工具名和 JSON 参数。

    输出字段：
        JSON 字符串；成功时包含工具实现返回的字段，失败时包含 ok、error 和
        message，供下一轮模型响应使用。
    """

    tool_name = tool_call.function.name

    try:
        arguments = json.loads(tool_call.function.arguments)
    except (json.JSONDecodeError, TypeError) as error:
        result = {
            "ok": False,
            "error": "INVALID_TOOL_ARGUMENTS",
            "message": str(error),
        }
        return json.dumps(result, ensure_ascii=False)

    if not isinstance(arguments, dict):
        result = {
            "ok": False,
            "error": "INVALID_TOOL_ARGUMENTS",
            "message": "工具参数必须是 JSON 对象",
        }
        return json.dumps(result, ensure_ascii=False)

    handler = TOOL_HANDLERS.get(tool_name)

    if handler is None:
        result = {
            "ok": False,
            "error": "UNKNOWN_TOOL",
            "message": f"没有注册工具 {tool_name}",
        }
        return json.dumps(result, ensure_ascii=False)

    try:
        result = handler(**arguments)
    except (TypeError, ValueError) as error:
        result = {
            "ok": False,
            "error": "TOOL_EXECUTION_ERROR",
            "message": str(error),
        }

    return json.dumps(result, ensure_ascii=False)


def agent_loop(
    client: Any,
    model: ModelConfig,
    messages: list[dict[str, Any]],
) -> str | None:
    """持续执行模型请求的工具，直到模型决定直接回复。"""

    while True:
        response = client.chat.completions.create(
            model=model.model_id,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
            tools=TOOLS,
            max_tokens=8000,
        )
        response_message = response.choices[0].message
        messages.append(response_message.model_dump(exclude_none=True))

        tool_calls = response_message.tool_calls or []
        if not tool_calls:
            return response_message.content

        for tool_call in tool_calls:
            trigger_hooks("PreToolUse", tool_call)
            tool_result = approval_middleware(
                tool_call,
                execute_tool,
            )
            trigger_hooks("PostToolUse", tool_call, tool_result)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )
