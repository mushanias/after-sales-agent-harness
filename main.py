"""售后处理 Agent 的最小模型—工具循环。"""

from __future__ import annotations

import json
import os
from typing import Any


SYSTEM_PROMPT = """你是售后处理 Agent。
当用户提供订单号并询问订单信息时，使用 lookup_order 查询。
只能根据工具返回的信息回答，不要编造订单或处理结果。
"""

TOOLS = [
    {
        "name": "lookup_order",
        "description": "根据订单号查询订单的商品、状态和金额。",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "需要查询的订单号，例如 A1001。",
                }
            },
            "required": ["order_id"],
        },
    }
]

# 第一阶段使用本地数据，避免把真实电商系统接入和 Agent Loop 混在一起。
ORDERS = {
    "A1001": {"product": "无线耳机", "status": "已签收", "amount": 299.0},
    "A1002": {"product": "机械键盘", "status": "运输中", "amount": 499.0},
}


def lookup_order(order_id: str) -> str:
    """返回指定订单的模拟查询结果。"""

    order = ORDERS.get(order_id)
    if order is None:
        return json.dumps(
            {"found": False, "order_id": order_id}, ensure_ascii=False
        )
    return json.dumps(
        {"found": True, "order_id": order_id, **order}, ensure_ascii=False
    )


def agent_loop(client: Any, model: str, messages: list[dict[str, Any]]) -> None:
    """持续执行模型请求的工具，直到模型决定直接回复。"""

    while True:
        response = client.messages.create(
            model=model,
            system=SYSTEM_PROMPT,
            messages=messages,
            tools=TOOLS,
            max_tokens=1024,
        )
        messages.append({"role": "assistant", "content": response.content})

        tool_calls = [
            block
            for block in response.content
            if getattr(block, "type", None) == "tool_use"
        ]
        if not tool_calls:
            return

        results = []
        for block in tool_calls:
            order_id = block.input.get("order_id")
            if block.name != "lookup_order":
                output = f"Error: unknown tool {block.name}"
            elif not isinstance(order_id, str) or not order_id.strip():
                output = "Error: order_id must be a non-empty string"
            else:
                output = lookup_order(order_id.strip())

            print(f"[tool] {block.name}({block.input})")
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                }
            )

        # 工具结果必须作为一条完整消息回传，模型才能基于真实观察继续推理。
        messages.append({"role": "user", "content": results})


def main() -> None:
    """启动保留当前会话历史的命令行交互。"""

    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise SystemExit("请先安装依赖：pip install -r requirements.txt") from exc

    model = os.getenv("MODEL_ID")
    if not model:
        raise SystemExit("请先设置环境变量 MODEL_ID")

    client = Anthropic()
    history: list[dict[str, Any]] = []

    print("售后处理 Agent：输入问题开始，输入 q 退出。")
    while True:
        try:
            query = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if query.lower() in {"q", "quit", "exit"}:
            break
        if not query:
            continue

        history.append({"role": "user", "content": query})
        agent_loop(client, model, history)

        for block in history[-1]["content"]:
            if getattr(block, "type", None) == "text":
                print(block.text)


if __name__ == "__main__":
    main()
