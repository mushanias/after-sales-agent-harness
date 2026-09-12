"""售后处理 Agent 的最小模型—工具循环。"""

from __future__ import annotations

import json
import os
from typing import Any

from model_pool import DEFAULT_MODEL, MODEL_POOL, ModelConfig

SYSTEM_PROMPT = """你是售后处理 Agent。
当用户提供订单号并询问订单信息时，使用 lookup_order 查询。
只能根据工具返回的信息回答，不要编造订单或处理结果。
"""

TOOLS = [
    {
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
]

# 第一阶段使用本地数据，避免把真实电商系统接入和 Agent Loop 混在一起。
ORDERS = {
    "A1001": {"product": "无线耳机", "status": "已签收", "amount": 299.0},
    "A1002": {"product": "机械键盘", "status": "运输中", "amount": 499.0},
}

TOOL_HANDLERS={}

def execute_tool(tool_call: Any) -> str:
    """解析模型给出的工具调用，执行对应函数，并返回 JSON 字符串。"""
    tool_name = tool_call.function.name

    try:
        arguments = json.loads(tool_call.function.arguments)
    except json.JSONDecodeError as error:
        result = {
            "ok": False,
            "error": "INVALID_TOOL_ARGUMENTS",
            "message": str(error),
        }
        return json.dumps(result, ensure_ascii=False)

    handler = TOOL_HANDLERS.get(tool_name)
    if handler is None:
        result = {
            "ok": False,
            "error": "UNKNOWN_TOOL",
            "message": f"没有注册工具 {tool_name}",
        }
        return json.dumps(result, ensure_ascii=False)

    try:
        result = handler(**arguments)
    except (TypeError, ValueError) as error:
        result = {
            "ok": False,
            "error": "TOOL_EXECUTION_ERROR",
            "message": str(error),
        }

    return json.dumps(result, ensure_ascii=False)
# ========================================================

def agent_loop(
    client: Any,
    model: ModelConfig,
    messages: list[dict[str, Any]],
) -> None:
    """持续执行模型请求的工具，直到模型决定直接回复。"""

    while True:
        response = client.chat.completions.create(
            model=model.model_id,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
            tools=TOOLS,
            max_tokens=8000,
        )
        response_message = response.choices[0].message

        messages.append(response_message.model_dump(exclude_none=True))

        tool_calls = response_message.tool_calls or []
        if not tool_calls:
            return response_message.content

        for tool_call in tool_calls:
            messages.append(
                {
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": execute_tool(tool_call),
            }
            )



def main() -> None:
    """
    启动保留当前会话历史的命令行交互。
    上游通过ModelConfig来提供llm
    目前只支持openai，已经预留了连接池
    """

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise SystemExit("请先安装依赖：pip install -r requirements.txt") from exc

    model = MODEL_POOL[DEFAULT_MODEL]
    api_key = os.getenv(model.api_key_env)
    if not api_key:
        raise SystemExit(f"请先设置环境变量 {model.api_key_env}")

    client = OpenAI(api_key=api_key, base_url=model.base_url)
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

        content = history[-1]["content"]
        if content:
            print(content)


if __name__ == "__main__":
    main()
