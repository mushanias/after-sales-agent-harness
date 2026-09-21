"""加载当前售后 Agent 使用的静态业务知识。"""

from pathlib import Path

from knowledge.refund_policy import REFUND_POLICY


STORE_POLICY_PATH = Path(__file__).with_name("store_policy.md")


def load_knowledge_base() -> str:
    """
    合并法律规则摘要与商家提供的店规原文。

    订单状态等运行事实不从这里加载，仍必须通过订单查询工具取得。
    """

    store_policy = STORE_POLICY_PATH.read_text(encoding="utf-8").strip()
    return f"""## 法律规则摘要

{REFUND_POLICY}

## 商家店规原文

{store_policy}"""


KNOWLEDGE_BASE = load_knowledge_base()
