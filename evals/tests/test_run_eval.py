"""评估器自身的隔离性与主链路冒烟测试。"""

from __future__ import annotations

import importlib
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch


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
    """按顺序返回模型消息，并保留每次请求收到的上下文。"""

    def __init__(self, messages: list[FakeMessage]) -> None:
        self._messages = iter(messages)
        self.contexts: list[list[dict[str, Any]]] = []

    def create(self, **kwargs: Any) -> Any:
        """返回下一条模拟响应。"""

        self.contexts.append(kwargs["messages"])
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

    def test_loop_refreshes_context_and_keeps_turn_history(self) -> None:
        """工具结果进入下一次请求，下一轮保留历史，审批及 Hook 仍正常触发。"""

        from session import Session

        loop_module = importlib.import_module("loop.agent_loop")
        tool_calls = [
            FakeToolCall("call-1", "lookup_order", {"order_id": "1"}),
            FakeToolCall("call-2", "lookup_order", {"order_id": "2"}),
        ]
        completions = FakeCompletions(
            [
                FakeMessage(tool_calls=tool_calls),
                FakeMessage(content="Both records found"),
                FakeMessage(content="Next turn complete"),
            ]
        )
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        model = SimpleNamespace(model_id="fake-model")
        session = Session(system_prompt="System instructions", skills="lookup")
        session.add_user("Find two records")

        def hook_result(event_name: str, *args: Any) -> str | None:
            """模拟工具执行后的提醒文本。"""

            return "reminder" if event_name == "PostToolUse" else None

        with (
            patch.object(
                loop_module,
                "approval_middleware",
                side_effect=["record 1", "record 2"],
            ) as approval,
            patch.object(
                loop_module, "trigger_hooks", side_effect=hook_result
            ) as hooks,
        ):
            self.assertEqual(
                "Both records found", loop_module.agent_loop(client, model, session)
            )
            session.add_user("Continue")
            self.assertEqual(
                "Next turn complete", loop_module.agent_loop(client, model, session)
            )

        self.assertEqual(3, len(completions.contexts))
        self.assertEqual(
            ["system", "system", "user"],
            [message["role"] for message in completions.contexts[0]],
        )
        self.assertEqual(
            ["system", "system", "user", "assistant", "tool", "tool"],
            [message["role"] for message in completions.contexts[1]],
        )
        self.assertEqual("record 1\nreminder", completions.contexts[1][-2]["content"])
        self.assertEqual("record 2\nreminder", completions.contexts[1][-1]["content"])
        self.assertEqual(
            ["system", "system", "user", "assistant", "tool", "tool", "assistant", "user"],
            [message["role"] for message in completions.contexts[2]],
        )
        self.assertEqual("Next turn complete", session.history[-1]["content"])
        self.assertEqual(2, approval.call_count)
        for tool_call in tool_calls:
            approval.assert_any_call(tool_call, loop_module.execute_tool)
        self.assertEqual(
            [
                "PostModelResponse",
                "PreToolUse",
                "PostToolUse",
                "PreToolUse",
                "PostToolUse",
                "PostModelResponse",
                "PostModelResponse",
            ],
            [call.args[0] for call in hooks.call_args_list],
        )

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
