from enum import Enum


class Permissions(str, Enum):
    """定义工具执行前支持的三种权限等级。"""

    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


# 工具名 → 权限等级。未注册的工具按 DENY 处理。
TOOL_PERMISSIONS: dict[str, Permissions] = {
    "lookup_order": Permissions.ALLOW,
    "request_refund": Permissions.ASK,
}
