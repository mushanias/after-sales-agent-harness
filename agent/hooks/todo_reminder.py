"""Todo 计划更新提醒 Hook。"""

from typing import Any


_tool_calls_since_todo_write = 0
_REMINDER_INTERVAL = 3


def remind_todo_update(tool_call: Any, tool_result: str) -> str | None:
    """
    在 PostToolUse 阶段提醒模型及时更新 Todo 计划。

    调用方式：
        remind_todo_update(tool_call, tool_result)

    输入字段：
        tool_call：刚完成处理的模型工具调用对象。
        tool_result：该工具返回给模型的原始结果，当前只作为事件上下文传入。

    输出字段：
        str：连续三个工具调用都没有使用 todo_write 时返回提醒文本。
        None：尚未达到提醒时机，或者本次调用已经更新 Todo。

    当前边界：
        当前按 PostToolUse 触发次数计数，不区分这些工具是否来自同一轮模型
        响应。调用 todo_write 或发出一次提醒后，计数都会清零。
    """

    global _tool_calls_since_todo_write

    if tool_call.function.name == "todo_write":
        _tool_calls_since_todo_write = 0
        return None

    _tool_calls_since_todo_write += 1
    if _tool_calls_since_todo_write < _REMINDER_INTERVAL:
        return None

    _tool_calls_since_todo_write = 0
    return (
        "<reminder>如果当前任务包含多个步骤，请使用 todo_write 更新当前计划和"
        "步骤状态；简单任务可以忽略本提醒。</reminder>"
    )
