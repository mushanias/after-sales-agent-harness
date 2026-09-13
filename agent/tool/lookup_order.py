"""订单查询工具的模型声明与执行实现。"""

from typing import Any

from knowledge.order import ORDERS


ORDER_LOOKUP_TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_order",
        "description": "根据订单号查询商品、订单状态、物流状态和退款状态。",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "需要查询的订单号，例如 1001。",
                }
            },
            "required": ["order_id"],
        },
    },
}


def lookup_order(order_id: str) -> dict[str, Any]:
    """
    在模型需要根据订单号查询业务订单时调用。

    调用方式：
        lookup_order(order_id="1001")

    输入字段：
        order_id：用户提供的订单号，必须是非空字符串。

    输出字段：
        ok：是否查询成功。
        order：查询成功时返回订单字段的副本。
        error：失败时的稳定错误代码。
        message：失败原因，供模型向用户解释当前状态。

    当前边界：
        当前从 knowledge.order.ORDERS 读取模拟订单；以后替换数据来源时保持本函数
        的输入输出契约不变。
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

    return {"ok": True, "order": dict(order)}
