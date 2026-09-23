"""扫描 Skill 元数据并维护短目录注册表。"""

from __future__ import annotations

from pathlib import Path
from typing import Any


SKILLS_ROOT = Path(__file__).resolve().parent
SKILL_CATEGORIES = {"policy", "skills"}


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


def skills_catalog() -> str:
    """生成供初始上下文使用的 Skill 短目录。"""

    if not SKILLS:
        return "（暂无可用 Skill）"

    return "\n".join(
        (
            f"- name: {skill['name']}\n"
            f"  description: {skill['description']}\n"
            f"  category: {skill['category']}"
        )
        for skill in SKILLS.values()
    )


def get_skill(name: str) -> dict[str, Any] | None:
    """按注册名称返回 Skill 元数据和可信文件位置。"""

    return SKILLS.get(name)


def skill_names() -> list[str]:
    """返回当前已注册的 Skill 名称。"""

    return list(SKILLS)
