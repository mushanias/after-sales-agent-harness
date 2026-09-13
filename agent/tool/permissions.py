from enum import Enum

class Permissions(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"

# 工具名 → 权限等级。未注册的工具按 DENY 处理。
TOOL_PERMISSIONS: dict[str, Permissions] = {
    "get_order_status": Permissions.ALLOW,
    "request_refund":   Permissions.ASK,
}