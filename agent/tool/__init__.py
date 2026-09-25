"""提供给模型的工具声明与程序侧处理器。"""

from typing import Any

from model import ModelConfig

from .permissions import Permissions, TOOL_PERMISSIONS
from .lookup_order import ORDER_LOOKUP_TOOL, lookup_order
from .request_refund import REFUND_REQUEST_TOOL, request_refund
from .skill_tools import (
    LOAD_SKILL_TOOL,
    load_skill,
)
from .todo_write import TODO_WRITE_TOOL, todo_write
from .sub_agent import TASK_TOOL, create_sub_agent


TOOLS = [
    LOAD_SKILL_TOOL,
    ORDER_LOOKUP_TOOL,
    REFUND_REQUEST_TOOL,
    TODO_WRITE_TOOL,
]
TOOL_HANDLERS = {
    "load_skill": load_skill,
    "lookup_order": lookup_order,
    "request_refund": request_refund,
    "todo_write": todo_write,
}


def configure_tools(client: Any, model: ModelConfig) -> None:
    """使用当前模型运行环境完成需要运行时参数的工具注册。"""

    if not any(tool["function"]["name"] == "task" for tool in TOOLS):
        TOOLS.append(TASK_TOOL)
    TOOL_HANDLERS["task"] = create_sub_agent(client, model)


__all__ = [
    "TOOLS",
    "TOOL_HANDLERS",
    "configure_tools",
    "TOOL_PERMISSIONS",
    "Permissions",
]
