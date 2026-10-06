"""压缩契约与轻量历史裁剪策略的公开入口。"""

from .contracts import CompactionResult, Compactor
from .window_compactor import WindowCompactor

__all__ = ["CompactionResult", "Compactor", "WindowCompactor"]
