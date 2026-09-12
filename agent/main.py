"""售后处理 Agent 的最小模型—工具循环。"""

from __future__ import annotations

import os
from typing import Any

from loop import agent_loop
from model import DEFAULT_MODEL, MODEL_POOL


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

        content = agent_loop(client, model, history)
        if content:
            print(content)


if __name__ == "__main__":
    main()
