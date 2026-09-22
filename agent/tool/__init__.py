"""提供给模型的工具声明与程序侧处理器。"""

from .permissions import Permissions, TOOL_PERMISSIONS
from .lookup_order import ORDER_LOOKUP_TOOL, lookup_order
from .request_refund import REFUND_REQUEST_TOOL, request_refund
from .skill_tools import (
    LIST_SKILLS_TOOL,
    LOAD_SKILL_TOOL,
    list_skills,
    load_skill,
)
from .todo_write import TODO_WRITE_TOOL, todo_write


TOOLS = [
    LIST_SKILLS_TOOL,
    LOAD_SKILL_TOOL,
    ORDER_LOOKUP_TOOL,
    REFUND_REQUEST_TOOL,
    TODO_WRITE_TOOL,
]
TOOL_HANDLERS = {
    "list_skills": list_skills,
    "load_skill": load_skill,
    "lookup_order": lookup_order,
    "request_refund": request_refund,
    "todo_write": todo_write,
}

__all__ = ["TOOLS", "TOOL_HANDLERS", "TOOL_PERMISSIONS", "Permissions"]
