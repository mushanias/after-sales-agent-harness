"""上下文策略接口与窗口策略的公开入口。"""

from .context import Context
from .window_compactor import WindowContextProjector

__all__ = ["Context", "WindowContextProjector"]
