"""上下文投影插件负责取得历史副本，并交付本次模型使用的动态消息。"""

from typing import Any, Protocol

from session import Session


class ContextProjector(Protocol):
    """
    每个会话使用自己的插件实例；原文读取、工作消息、进度和压缩策略由插件维护。

    get_history 从 Session 取得只追加的完整原始历史副本；输出不包含 system 消息，
    必须保留当前问题、保持工具配对完整，并与插件内部状态隔离。
    调用方直接使用完整结果，不接收进度或参与压缩后的拼接。
    """

    def get_history(self, session: Session) -> list[dict[str, Any]]:
        """取得本会话的完整原文副本；实现不得暴露或修改 Session 内部历史。"""

        ...

    def build_messages(self, session: Session) -> list[dict[str, Any]]:
        """内部取得历史并更新工作上下文，返回可直接使用的完整动态消息副本。"""

        ...
