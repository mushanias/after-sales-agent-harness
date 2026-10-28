"""上下文投影接口与原文、裁剪两种实现的公开入口。"""

from .contracts import ContextProjector
from .history_projector import FullHistoryProjector
from .window_compactor import WindowContextProjector

__all__ = ["ContextProjector", "FullHistoryProjector", "WindowContextProjector"]
