"""售后处理 Skills 的公开加载入口。"""

from pathlib import Path


def load_skills() -> str:
    """按稳定顺序加载当前 Skills 包中的全部 Markdown 文件。"""

    # Skill 文件可以继续增加，调用方不需要知道具体文件名和位置。
    skill_files = sorted(Path(__file__).parent.glob("*.md"))
    return "\n\n".join(
        skill_file.read_text(encoding="utf-8").strip()
        for skill_file in skill_files
    )


__all__ = ["load_skills"]
