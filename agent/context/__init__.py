"""模型上下文的公开入口。"""

from .build_context import build_context
from .system_prompt import SYSTEM_PROMPT

__all__ = ["SYSTEM_PROMPT", "build_context"]
