"""Skill 加载工具的模型声明与执行实现。"""

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
    """
    按 Skills 短目录中的注册名称读取完整内容。

    本工具只读取知识，不执行订单、退款或其他业务操作；名称不会被当作文件路径。
    """

    return skill.load_skill(name)
