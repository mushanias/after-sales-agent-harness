"""使用 SQLite 保存订单运行时事实。"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from .mock_orders import ORDERS as MOCK_ORDERS


DATABASE_PATH = Path(__file__).parent.parent / "orders.db"


def _initialize_order_store(connection: sqlite3.Connection) -> None:
    """
    创建订单表，并仅在空表中写入手工模拟订单。

    调用方式：
        _initialize_order_store(connection)

    输入字段：
        connection：当前 SQLite 连接。

    输出字段：
        无返回值；初始化完成后提交事务。

    当前边界：
        mock_orders.py 只是首次种子，已有数据库状态不会被种子覆盖。
    """

    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            order_id TEXT PRIMARY KEY,
            product_name TEXT NOT NULL,
            purchased_at TEXT NOT NULL,
            shipping_status TEXT NOT NULL,
            received_at TEXT,
            refund_status TEXT
        )
        """
    )

    order_count = connection.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    if order_count == 0:
        connection.executemany(
            """
            INSERT INTO orders (
                order_id,
                product_name,
                purchased_at,
                shipping_status,
                received_at,
                refund_status
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    order["order_id"],
                    order["product_name"],
                    order["purchased_at"],
                    order["shipping_status"],
                    order["received_at"],
                    order["refund_status"],
                )
                for order in MOCK_ORDERS.values()
            ],
        )

    connection.commit()


def _connect() -> sqlite3.Connection:
    """
    打开当前订单数据库并确保基础表已经初始化。

    调用方式：
        connection = _connect()

    输入字段：
        无。

    输出字段：
        sqlite3.Connection：已经设置行字典访问方式的数据库连接。
    """

    connection = sqlite3.connect(DATABASE_PATH)
    connection.row_factory = sqlite3.Row
    _initialize_order_store(connection)
    return connection


def get_order(order_id: str) -> dict[str, Any] | None:
    """
    从 SQLite 查询指定订单的当前事实。

    调用方式：
        get_order("1001")

    输入字段：
        order_id：需要查询的订单号。

    输出字段：
        dict：当前数据库中的订单字段；订单不存在时返回 None。
    """

    with closing(_connect()) as connection:
        row = connection.execute(
            """
            SELECT
                order_id,
                product_name,
                purchased_at,
                shipping_status,
                received_at,
                refund_status
            FROM orders
            WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()

    return dict(row) if row is not None else None


def update_refund_status(
    order_id: str,
    refund_status: str,
) -> dict[str, Any] | None:
    """
    更新退款状态，并返回数据库提交后的订单事实。

    调用方式：
        update_refund_status("1001", "申请中")

    输入字段：
        order_id：需要更新的订单号。
        refund_status：需要保存的退款状态。

    输出字段：
        dict：更新成功并提交后的订单字段；订单不存在时返回 None。

    当前边界：
        只有数据库提交成功后才返回新状态，Tool 不再自行宣布状态变化。
    """

    with closing(_connect()) as connection:
        cursor = connection.execute(
            """
            UPDATE orders
            SET refund_status = ?
            WHERE order_id = ?
            """,
            (refund_status, order_id),
        )
        if cursor.rowcount == 0:
            return None

        row = connection.execute(
            """
            SELECT
                order_id,
                product_name,
                purchased_at,
                shipping_status,
                received_at,
                refund_status
            FROM orders
            WHERE order_id = ?
            """,
            (order_id,),
        ).fetchone()
        connection.commit()

    return dict(row)
