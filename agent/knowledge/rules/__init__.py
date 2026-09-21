"""法律规则与商家规则的公开加载入口。"""

from pathlib import Path


def load_rules() -> str:
    """按稳定顺序加载当前规则包中的全部 Markdown 文件。"""

    # 法律规则和商家规则使用相同格式，新增文件不需要修改加载代码。
    rule_files = sorted(Path(__file__).parent.glob("*.md"))
    return "\n\n".join(
        rule_file.read_text(encoding="utf-8").strip()
        for rule_file in rule_files
    )


__all__ = ["load_rules"]
