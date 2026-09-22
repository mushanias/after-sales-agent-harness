"""组装单次模型调用需要的上下文。"""

from __future__ import annotations

from typing import Any


def build_context(
    system_prompt: str,
) -> list[dict[str, Any]]:
    """使用固定系统提示构造初始消息。"""

    return [{"role": "system", "content": system_prompt}]
