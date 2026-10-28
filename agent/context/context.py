"""上下文投影插件负责取得历史副本，并交付本次模型使用的动态消息。"""

from typing import Any, Protocol

from session import Session


class Context(Protocol):
    """
    每个会话使用自己的插件实例；原文读取、工作消息、进度和压缩策略由插件维护。

    Loop 只调用 build_messages；策略内部按 get_history → compact_history 构建消息。
    消息字段以 session/session.py 的 UserMessage、AssistantMessage、ToolCall、
    ToolResult 为准；history 不包含 system，模型消息的 content 可能不存在。
    输出必须保留当前未结束轮次、保持工具配对完整，并与策略内部状态隔离。
    调用方直接使用完整结果，不接收进度或参与压缩后的拼接。
    """

    def get_history(self, session: Session) -> list[dict[str, Any]]:
        """取得本会话的完整原文副本；实现不得暴露或修改 Session 内部历史。"""
        ...

    def compact_history(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """接收完整历史副本，返回完整工作消息；无压缩策略可原样返回输入。

        有状态策略仅在加工成功后更新缓存和进度，返回值不得暴露内部缓存。
        """
        ...

    def build_messages(self, session: Session) -> list[dict[str, Any]]:
        """读取历史副本并调用具体策略，交付本次模型使用的完整动态消息。"""
        ...
