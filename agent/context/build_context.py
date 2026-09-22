"""组装单次模型调用需要的上下文。"""

from __future__ import annotations

from typing import Any


def build_context(
    system_prompt: str,
    skills_catalog: str,
) -> list[dict[str, Any]]:
    """组合固定系统提示和 Skill 短目录，返回初始消息。"""

    return [
        {"role": "system", "content": system_prompt},
        {
            "role": "system",
            "content": (
                "可用 Skills：\n"
                f"{skills_catalog}\n\n"
                "根据每项 Skill 的 description 判断是否适用于当前任务；"
                "需要完整内容时调用 load_skill(name)。"
            ),
        },
    ]
