"""模型工具调用观察 Hook。"""

from typing import Any


def observe_tool_call(tool_call: Any) -> None:
    """
    在 PreToolUse 阶段观察模型请求调用的单个工具。

    调用方式：
        observe_tool_call(tool_call)

    输入字段：
        tool_call：模型 SDK 返回的单个工具调用对象。

    输出字段：
        无返回值；只输出工具名和原始参数，不修改调用，也不执行工具。
    """

    print(
        "[hook:tool_call] "
        f"name={tool_call.function.name} "
        f"arguments={tool_call.function.arguments}"
    )
