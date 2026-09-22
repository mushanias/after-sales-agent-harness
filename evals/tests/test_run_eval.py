"""评估器自身的隔离性与主链路冒烟测试。"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any


EVAL_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = EVAL_ROOT.parent
AGENT_ROOT = PROJECT_ROOT / "agent"
sys.path.insert(0, str(EVAL_ROOT))
sys.path.insert(0, str(AGENT_ROOT))

# 测试不创建真实模型客户端；项目模型模块只需要这个加载入口存在。
sys.modules.setdefault(
    "dotenv",
    SimpleNamespace(load_dotenv=lambda: None),
)

import run_eval


class FakeToolCall:
    """提供 Agent Loop 所需的最小工具调用形状。"""

    def __init__(self, call_id: str, name: str, arguments: dict[str, Any]) -> None:
        self.id = call_id
        self.function = SimpleNamespace(
            name=name,
            arguments=json.dumps(arguments, ensure_ascii=False),
        )


class FakeMessage:
    """提供 Agent Loop 所需的最小模型消息形状。"""

    def __init__(
        self,
        content: str | None = None,
        tool_calls: list[FakeToolCall] | None = None,
    ) -> None:
        self.content = content
        self.tool_calls = tool_calls

    def model_dump(self, exclude_none: bool = True) -> dict[str, Any]:
        """返回可以追加到消息历史的字典。"""

        message: dict[str, Any] = {"role": "assistant"}
        if self.content is not None:
            message["content"] = self.content
        if self.tool_calls:
            message["tool_calls"] = [
                {
                    "id": tool_call.id,
                    "type": "function",
                    "function": {
                        "name": tool_call.function.name,
                        "arguments": tool_call.function.arguments,
                    },
                }
                for tool_call in self.tool_calls
            ]
        return message


class FakeCompletions:
    """按顺序返回预先定义的模型消息。"""

    def __init__(self, messages: list[FakeMessage]) -> None:
        self._messages = iter(messages)

    def create(self, **kwargs: Any) -> Any:
        """返回下一条模拟响应。"""

        return SimpleNamespace(
            choices=[SimpleNamespace(message=next(self._messages))],
        )


class EvalRunnerTests(unittest.TestCase):
    """验证数据集结构和临时数据库隔离。"""

    def test_suite_is_valid(self) -> None:
        """第一版数据集应包含十二个唯一案例。"""

        suite = run_eval.load_suite(run_eval.DEFAULT_SUITE_PATH)
        case_ids = [case["id"] for case in suite["cases"]]
        self.assertEqual(12, len(case_ids))
        self.assertEqual(12, len(set(case_ids)))

    def test_live_path_uses_temporary_database(self) -> None:
        """真实 Loop 和工具执行不得修改项目订单数据库。"""

        suite = run_eval.load_suite(run_eval.DEFAULT_SUITE_PATH)
        case = next(
            case
            for case in suite["cases"]
            if case["id"] == "eligible_explicit_application"
        )
        messages = [
            FakeMessage(
                tool_calls=[
                    FakeToolCall(
                        "call-lookup",
                        "lookup_order",
                        {"order_id": "EVAL-1003"},
                    )
                ]
            ),
            FakeMessage(
                tool_calls=[
                    FakeToolCall(
                        "call-refund",
                        "request_refund",
                        {"order_id": "EVAL-1003"},
                    )
                ]
            ),
            FakeMessage(content="退款申请已提交，当前状态为申请中。"),
        ]
        client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=FakeCompletions(messages),
            )
        )
        model = SimpleNamespace(model_id="fake-model")

        production_database = (
            AGENT_ROOT / "knowledge" / "facts" / "orders.db"
        )
        original_bytes = (
            production_database.read_bytes()
            if production_database.exists()
            else None
        )

        result = run_eval.run_case(
            case,
            suite["fixed_date"],
            client,
            model,
            maximum_model_calls=8,
        )

        current_bytes = (
            production_database.read_bytes()
            if production_database.exists()
            else None
        )
        self.assertTrue(result["automatic_passed"])
        self.assertEqual(original_bytes, current_bytes)


if __name__ == "__main__":
    unittest.main()
