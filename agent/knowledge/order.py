"""当前用于业务闭环验证的模拟订单数据。"""


ORDERS = {
    "1001": {
        "order_id": "1001",
        "status": "已发货",
        "shipping_status": "运输中",
        "product_name": "无线耳机",
        "product_category": "HiFi耳机",
        "received_at": None,
        "return_condition": None,
        "no_reason_return_exclusion_confirmed": False,
        "refund_status": None,
    },
    "1002": {
        "order_id": "1002",
        "status": "已完成",
        "shipping_status": "已签收",
        "product_name": "hifi耳机",
        "product_category": "HiFi耳机",
        "received_at": "2026-09-10",
        "return_condition": "商品、配件、标识和赠品齐全，仅做合理查验",
        "no_reason_return_exclusion_confirmed": False,
        "refund_status": None,
    },
}
