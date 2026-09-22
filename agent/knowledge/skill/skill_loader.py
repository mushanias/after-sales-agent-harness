"""扫描 Skill 元数据并按注册名称加载完整内容。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError


class SkillDocument(BaseModel):
    """保存一个 Skill 对外目录信息及其完整 Markdown 内容。"""

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    category: Literal["policy", "skills"]
    content: str = Field(min_length=1)


class SkillLoader:
    """从固定知识目录建立 Skill 注册表，并只允许通过名称读取。"""

    def __init__(self, skills_dir: Path) -> None:
        self.skills_dir = skills_dir
        self._skills: dict[str, SkillDocument] = {}
        self._scan()

    @staticmethod
    def _parse_frontmatter(content: str) -> dict[str, str]:
        """读取当前 Skill 契约需要的简单 YAML 字符串字段。"""

        lines = content.splitlines()
        if not lines or lines[0].strip() != "---":
            raise ValueError("SKILL.md 缺少 YAML frontmatter")

        try:
            closing_index = lines[1:].index("---") + 1
        except ValueError as error:
            raise ValueError("SKILL.md 的 YAML frontmatter 未闭合") from error

        metadata: dict[str, str] = {}
        for line in lines[1:closing_index]:
            stripped_line = line.strip()
            if not stripped_line or stripped_line.startswith("#"):
                continue

            key, separator, value = stripped_line.partition(":")
            if not separator:
                raise ValueError(f"无法解析 Skill 元数据：{line}")
            metadata[key.strip()] = value.strip().strip("\"'")

        return metadata

    def _scan(self) -> None:
        """扫描分类目录中的 SKILL.md，并建立名称到内容的注册表。"""

        self._skills.clear()
        if not self.skills_dir.exists():
            return

        skills_root = self.skills_dir.resolve()
        for manifest in sorted(self.skills_dir.rglob("SKILL.md")):
            resolved_manifest = manifest.resolve()
            if not manifest.is_file() or not resolved_manifest.is_relative_to(
                skills_root
            ):
                continue

            content = manifest.read_text(encoding="utf-8").strip()
            metadata = self._parse_frontmatter(content)
            try:
                skill = SkillDocument(
                    name=metadata.get("name", ""),
                    description=metadata.get("description", ""),
                    category=metadata.get("category", ""),
                    content=content,
                )
            except ValidationError as error:
                raise ValueError(f"无效的 Skill 元数据：{manifest}") from error

            relative_parts = manifest.relative_to(self.skills_dir).parts
            if not relative_parts or relative_parts[0] != skill.category:
                raise ValueError(
                    f"Skill category 与所在目录不一致：{manifest}"
                )
            if skill.name in self._skills:
                raise ValueError(f"Skill 名称重复：{skill.name}")

            self._skills[skill.name] = skill

    def catalog(self) -> str:
        """返回供模型判断适用范围的短目录。"""

        if not self._skills:
            return "（暂无可用 Skill）"

        return "\n".join(
            f"- [{skill.category}] {skill.name}: {skill.description}"
            for skill in self._skills.values()
        )

    def load(self, name: str) -> dict[str, Any]:
        """按注册名称返回完整 Skill，不接受文件路径。"""

        normalized_name = name.strip() if isinstance(name, str) else ""
        skill = self._skills.get(normalized_name)
        if skill is None:
            available = list(self._skills)
            return {
                "ok": False,
                "error": "UNKNOWN_SKILL",
                "message": f"没有找到 Skill {normalized_name or name}",
                "available": available,
            }

        return {
            "ok": True,
            "name": skill.name,
            "category": skill.category,
            "content": skill.content,
        }


_SKILL_LOADER = SkillLoader(Path(__file__).parent)


def skills_catalog() -> str:
    """返回所有 Skill 的名称、说明和分类。"""

    return _SKILL_LOADER.catalog()


def load_skill(name: str) -> dict[str, Any]:
    """按名称加载一个完整 Skill。"""

    return _SKILL_LOADER.load(name)
