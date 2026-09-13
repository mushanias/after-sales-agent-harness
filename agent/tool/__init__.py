"""提供给模型的工具声明与程序侧处理器。"""

from .permissions import Permissions, TOOL_PERMISSIONS
from .lookup_order import ORDER_LOOKUP_TOOL, lookup_order
from .request_refund import REFUND_REQUEST_TOOL, request_refund

TOOLS = [ORDER_LOOKUP_TOOL, REFUND_REQUEST_TOOL]
TOOL_HANDLERS = {
    "lookup_order": lookup_order,
    "request_refund": request_refund,
}

__all__ = ["TOOLS", "TOOL_HANDLERS", "TOOL_PERMISSIONS", "Permissions"]
