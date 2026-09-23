"""Skill 正文加载工具。"""

from __future__ import annotations

from typing import Any

from knowledge import skill


LOAD_SKILL_TOOL = {
    "type": "function",
    "function": {
        "name": "load_skill",
        "description": "根据 Skills 短目录中的名称加载完整政策规则或处理指导。",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "需要加载的 Skill 名称，必须来自 Skills 短目录。",
                }
            },
            "required": ["name"],
        },
    },
}


def load_skill(name: str) -> dict[str, Any]:
    """按短目录中的注册名称读取完整 SKILL.md。"""

    if not isinstance(name, str) or not name.strip():
        return {
            "ok": False,
            "error": "INVALID_SKILL_NAME",
            "message": "Skill 名称不能为空",
        }

    normalized_name = name.strip()
    registered_skill = skill.get_skill(normalized_name)
    if registered_skill is None:
        return {
            "ok": False,
            "error": "UNKNOWN_SKILL",
            "message": f"没有找到 Skill {normalized_name}",
            "available": skill.skill_names(),
        }

    try:
        content = registered_skill["manifest"].read_text(
            encoding="utf-8"
        ).strip()
    except OSError as error:
        return {
            "ok": False,
            "error": "SKILL_READ_ERROR",
            "message": str(error),
        }

    return {
        "ok": True,
        "name": registered_skill["name"],
        "category": registered_skill["category"],
        "content": content,
    }
