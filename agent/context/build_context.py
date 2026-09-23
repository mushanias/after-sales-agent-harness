"""组装单次模型调用需要的上下文。"""

from __future__ import annotations

from typing import Any


def build_context(
    system_prompt: str,
    skills: str,
) -> list[dict[str, Any]]:
    """按职责组合系统提示和 Skill 短目录。"""

    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "system",
            "content": f"可用 Skills 短目录：\n{skills}",
        },
    ]
