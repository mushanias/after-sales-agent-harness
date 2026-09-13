"""退款申请工具的模型声明与执行实现。"""

from typing import Any

from knowledge.order import ORDERS


REFUND_REQUEST_TOOL = {
    "type": "function",
    "function": {
        "name": "request_refund",
        "description": "在确认订单符合七天无理由规则后发起退款申请。该操作会改变业务状态。",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "需要发起退款的订单号，例如 1001。",
                }
            },
            "required": ["order_id"],
        },
    },
}


def request_refund(order_id: str) -> dict[str, Any]:
    """
    在用户明确要求为指定订单发起退款时调用。

    调用方式：
        request_refund(order_id="1001")

    输入字段：
        order_id：需要退款的订单号，必须是非空字符串。

    输出字段：
        ok：是否成功发起退款。
        order_id：成功发起退款的订单号。
        refund_status：退款申请成功后的状态。
        error：失败时的稳定错误代码。
        message：失败原因，供模型向用户解释当前状态。

    当前边界：
        当前修改 knowledge.order.ORDERS 中的 refund_status；以后替换数据来源时保持
        本函数的输入输出契约不变。当前不判断七天无理由资格。
    """

    if not isinstance(order_id, str) or not order_id.strip():
        return {
            "ok": False,
            "error": "INVALID_ORDER_ID",
            "message": "订单号不能为空",
        }

    normalized_order_id = order_id.strip()
    order = ORDERS.get(normalized_order_id)
    if order is None:
        return {
            "ok": False,
            "error": "ORDER_NOT_FOUND",
            "message": f"没有找到订单 {normalized_order_id}",
        }

    order["refund_status"] = "申请中"
    return {
        "ok": True,
        "order_id": normalized_order_id,
        "refund_status": order["refund_status"],
    }
