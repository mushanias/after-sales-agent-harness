"""Skill 目录与正文加载工具。"""

from __future__ import annotations

from pathlib import Path
from typing import Any


SKILLS_ROOT = Path(__file__).resolve().parents[1] / "knowledge" / "skill"
SKILL_CATEGORIES = {"policy", "skills"}


LIST_SKILLS_TOOL = {
    "type": "function",
    "function": {
        "name": "list_skills",
        "description": "列出可用 Skill 的名称、适用说明和分类，不加载完整正文。",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
}

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


def _read_frontmatter(manifest: Path) -> dict[str, str]:
    """只读取 SKILL.md 开头的 name、description 和 category。"""

    with manifest.open(encoding="utf-8") as skill_file:
        if skill_file.readline().strip() != "---":
            raise ValueError(f"SKILL.md 缺少 YAML frontmatter：{manifest}")

        frontmatter_lines: list[str] = []
        for line in skill_file:
            if line.strip() == "---":
                break
            frontmatter_lines.append(line)
        else:
            raise ValueError(f"SKILL.md 的 YAML frontmatter 未闭合：{manifest}")

    metadata: dict[str, str] = {}
    for line in frontmatter_lines:
        stripped_line = line.strip()
        if not stripped_line or stripped_line.startswith("#"):
            continue

        key, separator, value = stripped_line.partition(":")
        if not separator:
            raise ValueError(f"无法解析 Skill 元数据：{line.rstrip()}")
        metadata[key.strip()] = value.strip().strip("\"'")

    return metadata


def _scan_skills() -> dict[str, dict[str, Any]]:
    """扫描 Skill 元数据，返回名称到可信文件位置的映射。"""

    skills: dict[str, dict[str, Any]] = {}
    if not SKILLS_ROOT.exists():
        return skills

    resolved_root = SKILLS_ROOT.resolve()
    for manifest in sorted(SKILLS_ROOT.rglob("SKILL.md")):
        resolved_manifest = manifest.resolve()
        if not manifest.is_file() or not resolved_manifest.is_relative_to(
            resolved_root
        ):
            continue

        metadata = _read_frontmatter(manifest)
        name = metadata.get("name", "").strip()
        description = metadata.get("description", "").strip()
        category = metadata.get("category", "").strip()

        if not name or not description or category not in SKILL_CATEGORIES:
            raise ValueError(f"无效的 Skill 元数据：{manifest}")

        relative_parts = manifest.relative_to(SKILLS_ROOT).parts
        if not relative_parts or relative_parts[0] != category:
            raise ValueError(f"Skill category 与所在目录不一致：{manifest}")
        if name in skills:
            raise ValueError(f"Skill 名称重复：{name}")

        skills[name] = {
            "name": name,
            "description": description,
            "category": category,
            "manifest": resolved_manifest,
        }

    return skills


SKILLS = _scan_skills()


def list_skills() -> dict[str, Any]:
    """暴露 Skill 短目录，由模型根据 description 选择加载项。"""

    return {
        "ok": True,
        "skills": [
            {
                "name": skill["name"],
                "description": skill["description"],
                "category": skill["category"],
            }
            for skill in SKILLS.values()
        ],
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
    skill = SKILLS.get(normalized_name)
    if skill is None:
        return {
            "ok": False,
            "error": "UNKNOWN_SKILL",
            "message": f"没有找到 Skill {normalized_name}",
            "available": list(SKILLS),
        }

    try:
        content = skill["manifest"].read_text(encoding="utf-8").strip()
    except OSError as error:
        return {
            "ok": False,
            "error": "SKILL_READ_ERROR",
            "message": str(error),
        }

    return {
        "ok": True,
        "name": skill["name"],
        "category": skill["category"],
        "content": content,
    }
