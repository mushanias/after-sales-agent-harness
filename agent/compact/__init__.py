"""压缩契约与轻量历史裁剪策略的公开入口。"""

from .contracts import CompactionOutput, CompactionResult, CompactionSnapshot, Compactor
from .window_compactor import WindowCompactor

__all__ = [
    "CompactionOutput", "CompactionResult", "CompactionSnapshot", "Compactor", "WindowCompactor"
]
