"""Agent Loop 的 Hook 注册入口。"""

from typing import Any, Callable

from .loop_round_observer import observe_loop_round
from .todo_reminder import remind_todo_update
from .tool_call_observer import observe_tool_call


HookCallback = Callable[..., str | None]

HOOKS: dict[str, list[HookCallback]] = {
    "PostModelResponse": [],
    "PreToolUse": [],
    "PostToolUse": [],
}


def register_hook(event_name: str, callback: HookCallback) -> None:
    """
    把回调函数显式注册到指定的 Hook 事件。

    调用方式：
        register_hook("PreToolUse", callback)

    输入字段：
        event_name：HOOKS 中已经声明的事件名称。
        callback：事件触发时调用的函数。

    输出字段：
        无返回值；未知事件会抛出 ValueError。
    """

    if event_name not in HOOKS:
        raise ValueError(f"未知 Hook 事件: {event_name}")
    HOOKS[event_name].append(callback)


def trigger_hooks(event_name: str, *args: Any) -> str | None:
    """
    在 Loop 到达指定阶段时，依次触发该事件下显式注册的回调。

    调用方式：
        trigger_hooks("PostModelResponse", response_message)
        trigger_hooks("PreToolUse", tool_call)
        trigger_hooks("PostToolUse", tool_call, tool_result)

    输入字段：
        event_name：需要触发的 Hook 事件名称。
        args：按事件契约传给回调的位置参数。

    输出字段：
        str：第一个需要交给调用方处理的 Hook 结果。
        None：所有 Hook 都只观察了当前事件。
    """

    if event_name not in HOOKS:
        raise ValueError(f"未知 Hook 事件: {event_name}")

    for callback in HOOKS[event_name]:
        result = callback(*args)
        if result is not None:
            return result

    return None


register_hook("PostModelResponse", observe_loop_round)
register_hook("PreToolUse", observe_tool_call)
register_hook("PostToolUse", remind_todo_update)

__all__ = ["HOOKS", "register_hook", "trigger_hooks"]
