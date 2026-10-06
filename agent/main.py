"""售后处理 Agent 的最小模型—工具循环。"""

from __future__ import annotations

import os
from datetime import date

from compact import WindowCompactor
from knowledge import skill
from loop import agent_loop
from model import DEFAULT_MODEL, MODEL_POOL
from session import Session
from tool import configure_tools


SYSTEM_PROMPT = f"""你是声途 HiFi 店的售后处理 Agent。当前日期是 {date.today().isoformat()}。

你处理取消订单、物流异常、七天无理由退货、质量问题以及错发漏发咨询。

处理边界：
1. 需要判断具体订单时，用户未提供订单号就先询问；取得订单号后必须先使用
   lookup_order 查询，不能把用户口述当作订单系统事实。
2. 业务规则和处理指导存放在 Skills 中。根据上下文里的 Skill 短目录和
   每项 description 判断是否适用，需要完整内容时使用 load_skill 读取。
3. load_skill 只读取知识，不代表任何业务操作已经执行。
4. 知识中说明某项业务可以办理，不代表你已经执行。没有对应业务工具时，只能说明
   规则、收集所需信息并告知需要人工处理。
5. 订单工具结果优先于用户口述；法律规则优先于商家店规；案例不能替代当前订单事实。
6. 只能根据工具结果描述处理状态，不要编造订单、退款结果或到账时间。
7. 当请求需要多个步骤或处理多个订单时，先使用 todo_write 建立完整计划，并随着
   处理进度更新步骤状态；简单查询不需要创建 Todo。
8. 当一项独立任务需要多次工具调用、主对话只需要最终结果时，可以使用 task 委派。
   在 task 参数中写清目标和必要的已知事实；子 Agent 看不到当前对话。
"""


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
    configure_tools(client, model)
    session = Session(
        system_prompt=SYSTEM_PROMPT,
        skills=skill.skills_catalog(),
        compactor=WindowCompactor(),
    )

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

        session.add_user(query)
        session.compact_if_needed()

        content = agent_loop(client, model, session)
        if content:
            print(content)


if __name__ == "__main__":
    main()
