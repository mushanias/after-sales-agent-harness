"""当前用于业务闭环验证的模拟订单数据与字段契约。"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from knowledge.order_store import insert_order


class ShippingStatus(str, Enum):
    """定义当前模拟订单支持的物流状态。"""

    NOT_SHIPPED = "未发货"
    IN_TRANSIT = "已发货运输中"
    RECEIVED = "已签收"


class Order(BaseModel):
    """描述查询订单时可以确认的订单事实和当前退款状态。"""

    model_config = ConfigDict(validate_assignment=True)

    order_id: str
    product_name: str
    purchased_at: date
    shipping_status: ShippingStatus
    received_at: date | None = None
    refund_status: str | None = None

    @field_validator("order_id")
    @classmethod
    def normalize_order_id(cls, order_id: str) -> str:
        """去除订单号首尾空白，并拒绝空订单号。"""

        normalized_order_id = order_id.strip()
        if not normalized_order_id:
            raise ValueError("订单号不能为空")
        return normalized_order_id

    @model_validator(mode="after")
    def validate_shipping_time(self) -> Order:
        """保证物流状态、购买日期和签收日期不会互相矛盾。"""

        if self.shipping_status is ShippingStatus.RECEIVED:
            if self.received_at is None:
                raise ValueError("已签收订单必须提供签收日期")
            if self.received_at < self.purchased_at:
                raise ValueError("签收日期不能早于购买日期")
        elif self.received_at is not None:
            raise ValueError("未签收订单不能提供签收日期")

        return self


def set_order(order: Order) -> None:
    """
    把一笔经过字段校验的模拟订单加入当前订单表。

    调用方式：
        set_order(Order(...))

    输入字段：
        order：已经由 Order 契约校验的模拟订单。

    输出字段：
        无返回值；重复订单号会抛出 ValueError，避免静默覆盖已有订单。

    当前边界：
        这个函数只用于按需添加单笔订单；mock_orders.py 只负责空数据库的首次
        初始化。商品是否完好来自用户反馈，不属于订单数据。
    """

    insert_order(order.model_dump(mode="json"))
