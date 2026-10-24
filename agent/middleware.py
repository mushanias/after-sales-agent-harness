"""工具权限中间件。"""

from __future__ import annotations

from typing import Any, Callable

from tool import TOOL_PERMISSIONS, Permissions

from collections.abc import Awaitable

import asyncio

_APPROVAL_LOCK = asyncio.Lock()

def check_permission(tool_name: str) -> Permissions:
    """
    在权限中间件处理工具调用时查询工具的权限等级。

    调用方式：
        check_permission("request_refund")

    输入字段：
        tool_name：模型请求调用的工具名称。

    输出字段：
        Permissions：ALLOW、ASK 或 DENY；未注册工具默认返回 DENY。
    """

    return TOOL_PERMISSIONS.get(tool_name, Permissions.DENY)


async def approval_middleware(tool_call: Any, next_handler: Callable[[Any], Awaitable[str]]) -> str:
    """
    在工具真正执行前，根据权限等级决定是否调用下一个处理器。

    调用方式：
        approval_middleware(tool_call, execute_tool)

    输入字段：
        tool_call：模型 SDK 返回的单个工具调用对象。
        next_handler：权限允许后才调用的工具处理函数。

    输出字段：
        str：允许时返回工具处理结果；拒绝时返回拒绝原因。

    权限规则：
        ALLOW 直接执行；ASK 等待操作人确认；DENY 直接拒绝。
    """

    tool_name = tool_call.function.name
    permission = check_permission(tool_name)

    if permission is Permissions.ALLOW:
        return await next_handler(tool_call)

    if permission is Permissions.DENY:
        return f"工具 {tool_name} 已被禁用"

    if permission is Permissions.ASK:
        async with _APPROVAL_LOCK:
            print(f"\n工具调用请求: {tool_name}")
            print(f"参数: {tool_call.function.arguments}")

            while True:
                raw_choice = await asyncio.to_thread(
                    input,
                    "是否允许执行? (y/n): ",
                )
                choice = raw_choice.strip().lower()

                if choice in {"y", "yes"}:
                    approved = True
                    break

                if choice in {"n", "no"}:
                    approved = False
                    break

                print("请输入 y 或 n")

        if approved:
            return await next_handler(tool_call)

        return f"用户拒绝执行 {tool_name}"

    return f"未知权限等级: {permission}"
