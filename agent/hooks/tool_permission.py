"""工具执行前的权限检查 Hook。"""

from __future__ import annotations

from typing import Any

from tool import TOOL_PERMISSIONS, Permissions



def check_permission(tool_name: str) -> Permissions:
    return TOOL_PERMISSIONS.get(tool_name, Permissions.DENY)


def approval_middleware(tool_call: Any, next_handler) -> Any:
    tool_name = tool_call.function.name
    level = check_permission(tool_name)

    # 1
    if level is Permissions.ALLOW:
        return next_handler(tool_call)

    # 2
    if level is Permissions.DENY:
        return f"工具 {tool_name} 已被禁用"

    # 3
    if level is Permissions.ASK:
        print(f"\n工具调用请求: {tool_name}")
        print(f"参数: {tool_call.function.arguments}")
        while True:
            choice = input("是否允许执行? (y/n): ").strip().lower()
            if choice in ("y", "yes"):
                return next_handler(tool_call)
            if choice in ("n", "no"):
                return f"用户拒绝执行 {tool_name}"
            print("请输入 y 或 n")

    return f"未知权限等级: {level}"
