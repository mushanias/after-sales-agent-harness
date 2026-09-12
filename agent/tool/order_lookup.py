"""订单查询工具声明与模拟数据。"""


ORDER_LOOKUP_TOOL = {
    "type": "function",
    "function": {
        "name": "lookup_order",
        "description": "根据订单号查询订单的商品、状态和金额。",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "需要查询的订单号，例如 A1001。",
                }
            },
            "required": ["order_id"],
        },
    },
}


ORDERS = {
    "A1001": {"product": "无线耳机", "status": "已签收", "amount": 299.0},
    "A1002": {"product": "机械键盘", "status": "运输中", "amount": 499.0},
}
