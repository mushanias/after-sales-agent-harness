"""组装单次模型调用需要的上下文。"""

from __future__ import annotations

from typing import Any


def build_context(
    system_prompt: str,
    rules_context: str,
    skills_context: str,
) -> list[dict[str, Any]]:
    """按职责组合系统提示、业务规则和处理技能，返回初始消息。"""

    return [
        {"role": "system", "content": system_prompt},
        {"role": "system", "content": f"业务规则：\n{rules_context}"},
        {"role": "system", "content": f"处理 Skills：\n{skills_context}"},
    ]
