"""Agent Loop 轮次观察 Hook。"""

from typing import Any


_loop_count = 0


def observe_loop_round(response_message: Any) -> None:
    """
    在模型每次返回响应后输出当前 Agent Loop 轮次。

    调用方式：
        observe_loop_round(response_message)

    输入字段：
        response_message：模型本轮返回的消息对象。

    输出字段：
        无返回值；只输出轮次、工具调用数量和 Loop 是否继续。

    当前边界：
        Hook 在内存中持有计数；模型返回无工具响应时清零，因此下一次正常请求
        会从 1 开始。模型调用中途异常时暂不处理计数重置。
    """

    global _loop_count

    _loop_count += 1
    tool_call_count = len(response_message.tool_calls or [])
    should_continue = tool_call_count > 0
    print(
        "[hook:loop] "
        f"round={_loop_count} "
        f"tool_calls={tool_call_count} "
        f"continue={should_continue}"
    )

    if not should_continue:
        _loop_count = 0
