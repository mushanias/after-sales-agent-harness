"""模型工具调用观察 Hook。"""

from typing import Any


def observe_tool_calls(response_message: Any) -> None:
    """
    观察模型在本轮响应中请求调用的工具。

    调用时机：
        模型响应写入消息历史之后、工具真正执行之前。

    接收内容：
        response_message：模型返回的完整 assistant 消息。

    行为边界：
        只输出工具名和模型生成的原始参数，不修改响应，也不执行工具。
    """

    for tool_call in response_message.tool_calls or []:
        print(
            "[hook:tool_call] "
            f"name={tool_call.function.name} "
            f"arguments={tool_call.function.arguments}"
        )
