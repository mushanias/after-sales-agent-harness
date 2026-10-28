"""售后 Agent 的工具执行与核心循环。"""

from __future__ import annotations

import json
from typing import Any

from compact import ContextProjector, FullHistoryProjector
from hooks import trigger_hooks
from middleware import approval_middleware
from model import ModelConfig
from session import Session
from tool import TOOL_HANDLERS, TOOLS
import inspect
import asyncio
# ====================稍后把这部分提取出来，保持核心文件的干净
async def execute_tool(tool_call: Any) -> str:
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

        if inspect.isawaitable(result):
            result = await result

    except (TypeError, ValueError) as error:
        result = {
            "ok": False,
            "error": "TOOL_EXECUTION_ERROR",
            "message": str(error),
        }

    return json.dumps(result, ensure_ascii=False)

async def run_one_tool(tool_call: Any) -> str:
    """执行一次工具调用，返回结果，由父 Loop 写入会话。"""

    trigger_hooks("PreToolUse", tool_call)

    result = await approval_middleware(
        tool_call,
        execute_tool,
    )

    reminder = trigger_hooks("PostToolUse", tool_call, result)
    if reminder is not None:
        result = f"{result}\n{reminder}"

    return result


def build_request_messages(
    system_prompt: str,
    skills: str,
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """包装固定系统输入与插件交付的完整动态消息，不处理压缩或增量拼接。"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": f"可用 Skills 短目录：\n{skills}"},
    ] + messages
# ==========


# 我们使用投影
async def agent_loop(
    client: Any,
    model: ModelConfig,
    session: Session,
    projector: ContextProjector | None = None,
) -> str | None:
    """向投影器请求工作消息，并记录回复、工具结果，直到模型直接回复。"""

    if projector is None:
        projector = FullHistoryProjector()

    while True:
        # 每次请求前检查，覆盖本轮工具返回大段文本的情况。
        messages = projector.build_messages(session)
        response = await client.chat.completions.create(
            model=model.model_id,
            messages=build_request_messages(session.system_prompt, session.skills, messages),
            tools=TOOLS,
            max_tokens=8000,
        )
        response_message = response.choices[0].message
        trigger_hooks("PostModelResponse", response_message)
        session.add_assistant(response_message.model_dump(exclude_none=True))

        tool_calls = response_message.tool_calls or []
        if not tool_calls:
            return response_message.content

        results = await asyncio.gather(
            *(run_one_tool(call) for call in tool_calls),
            return_exceptions=True,
        )

        for call, result in zip(tool_calls, results):
            if isinstance(result, BaseException):
                raise result

            session.add_tool_result(call.id, result)
