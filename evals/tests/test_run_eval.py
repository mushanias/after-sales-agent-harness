"""评估器自身的隔离性与主链路冒烟测试。"""

from __future__ import annotations

import asyncio
import importlib
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch


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


class AsyncFakeCompletions(FakeCompletions):
    """提供主 Loop 使用的异步模型接口，仍只返回内存中的模拟消息。"""

    async def create(self, **kwargs: Any) -> Any:
        """异步返回下一条模拟响应。"""

        return super().create(**kwargs)


class EvalRunnerTests(unittest.IsolatedAsyncioTestCase):
    """验证数据集结构和临时数据库隔离。"""

    def test_suite_is_valid(self) -> None:
        """第一版数据集应包含十二个唯一案例。"""

        suite = run_eval.load_suite(run_eval.DEFAULT_SUITE_PATH)
        case_ids = [case["id"] for case in suite["cases"]]
        self.assertEqual(12, len(case_ids))
        self.assertEqual(12, len(set(case_ids)))

    async def test_loop_refreshes_context_and_keeps_turn_history(self) -> None:
        """工具结果进入下一次请求，下一轮保留历史，审批及 Hook 仍正常触发。"""

        from context import WindowContextProjector
        from session import Session

        loop_module = importlib.import_module("loop.agent_loop")
        tool_calls = [
            FakeToolCall("call-1", "lookup_order", {"order_id": "1"}),
            FakeToolCall("call-2", "lookup_order", {"order_id": "2"}),
        ]
        completions = AsyncFakeCompletions(
            [
                FakeMessage(tool_calls=tool_calls),
                FakeMessage(content="Both records found"),
                FakeMessage(content="Next turn complete"),
            ]
        )
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        model = SimpleNamespace(model_id="fake-model")
        session = Session(system_prompt="System instructions", skills="lookup")
        context = WindowContextProjector()
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
                "Both records found", await loop_module.agent_loop(client, model, session, context)
            )
            session.add_user("Continue")
            self.assertEqual(
                "Next turn complete", await loop_module.agent_loop(client, model, session, context)
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

    async def test_loop_accepts_plain_message_list_plugin(self) -> None:
        """Loop 只请求投影消息，不读取历史，也不接收插件的进度字段。"""

        from context import Context
        from session import Session

        loop_module = importlib.import_module("loop.agent_loop")
        session = Session("固定说明", "技能目录")
        session.add_user("旧问题")
        session.add_assistant({"role": "assistant", "content": "旧回答"})
        session.add_user("当前问题")
        original_history = session.history
        projected = [
            {"role": "assistant", "content": "插件提供的旧轮次摘要"},
            original_history[-1],
        ]
        plugin = Mock(spec=Context)
        plugin.build_messages.return_value = projected
        completions = AsyncFakeCompletions([FakeMessage(content="最终回答")])
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))

        with patch.object(loop_module, "trigger_hooks", return_value=None):
            answer = await loop_module.agent_loop(
                client, SimpleNamespace(model_id="fake-model"), session, context=plugin,
            )

        plugin.build_messages.assert_called_once_with(session)
        self.assertEqual("最终回答", answer)
        self.assertEqual(projected, completions.contexts[0][2:])
        self.assertEqual(
            ["固定说明", "可用 Skills 短目录：\n技能目录"],
            [message["content"] for message in completions.contexts[0][:2]],
        )
        self.assertEqual(original_history, session.history[:-1])

    async def test_loop_uses_compacted_context_and_receives_new_tool_results(self) -> None:
        """裁剪后的上下文进入真实 Loop，新工具结果仍进入下一次模拟模型请求。"""

        from context import WindowContextProjector
        from session import Session

        loop_module = importlib.import_module("loop.agent_loop")
        context = WindowContextProjector(max_chars=1)
        session = Session("固定说明", "技能目录")
        for turn in range(1, 6):
            session.add_user(f"第 {turn} 轮问题")
            session.add_assistant({"role": "assistant", "content": "原始回答" * 300})
        session.add_user("查询两个订单")
        original_history = session.history
        expected_context = loop_module.build_request_messages(
            session.system_prompt, session.skills, context.build_messages(session),
        )
        self.assertLess(len(expected_context), len(original_history) + 2)
        tool_calls = [
            FakeToolCall("new-1", "lookup_order", {"order_id": "1"}),
            FakeToolCall("new-2", "load_skill", {"name": "demo"}),
        ]
        completions = AsyncFakeCompletions([
            FakeMessage(tool_calls=tool_calls),
            FakeMessage(content="两个订单已查询"),
        ])
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        model = SimpleNamespace(model_id="fake-model")

        started = set()
        both_started = asyncio.Event()

        async def simulated_tool(call, handler):
            """两种工具都启动后才能返回，串行调度会超时而失败。"""

            started.add(call.id)
            if len(started) == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=1)
            return {"new-1": "订单一", "new-2": "技能内容"}[call.id]

        with (
            patch.object(loop_module, "approval_middleware", side_effect=simulated_tool),
            patch.object(loop_module, "trigger_hooks", return_value=None),
        ):
            answer = await loop_module.agent_loop(client, model, session, context)

        self.assertEqual("两个订单已查询", answer)
        self.assertEqual(expected_context, completions.contexts[0])
        self.assertEqual(expected_context, completions.contexts[1][:-3])
        self.assertEqual(
            ["assistant", "tool", "tool"],
            [message["role"] for message in completions.contexts[1][-3:]],
        )
        self.assertEqual("订单一", completions.contexts[1][-2]["content"])
        self.assertEqual("技能内容", completions.contexts[1][-1]["content"])
        self.assertEqual(
            ["new-1", "new-2"],
            [message["tool_call_id"] for message in completions.contexts[1][-2:]],
        )
        self.assertEqual(original_history, session.history[:len(original_history)])
        self.assertEqual(answer, session.history[-1]["content"])

    async def test_loop_shortens_large_tool_result_before_next_model_request(self) -> None:
        """首轮工具返回大文本后立即缩短，后续轮次复用结果且不再次执行工具。"""

        from context import WindowContextProjector
        from session import Session

        loop_module = importlib.import_module("loop.agent_loop")
        context = WindowContextProjector(max_tool_result_chars=512)
        session = Session("固定说明", "技能目录")
        session.add_user("读取规则并提交模拟退款")
        original_text = "规则开头。" + "演示正文。" * 2000 + "规则结尾。"
        short_result = "模拟退款已提交，编号 RF001"
        tool_calls = [
            FakeToolCall("large-result", "load_skill", {"name": "demo"}),
            FakeToolCall("refund-result", "request_refund", {"order_id": "demo"}),
        ]
        completions = AsyncFakeCompletions([
            FakeMessage(tool_calls=tool_calls),
            FakeMessage(content="模拟处理完毕"),
            FakeMessage(content="下一轮解释完毕"),
        ])
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        model = SimpleNamespace(model_id="fake-model")

        with (
            patch.object(
                loop_module, "approval_middleware", side_effect=[original_text, short_result]
            ) as approval,
            patch.object(loop_module, "trigger_hooks", return_value=None),
        ):
            self.assertEqual("模拟处理完毕", await loop_module.agent_loop(client, model, session, context))
            session.add_user("继续解释")
            self.assertEqual("下一轮解释完毕", await loop_module.agent_loop(client, model, session, context))

        messages = context.build_messages(session)
        shortened = messages[2]["content"]
        self.assertEqual(512, len(shortened))
        self.assertEqual(original_text, session.history[2]["content"])
        self.assertEqual(len(session.history), len(messages))
        self.assertEqual(2, approval.call_count)
        self.assertEqual(3, len(completions.contexts[0]))
        for request_context in completions.contexts[1:]:
            tool_messages = [message for message in request_context if message["role"] == "tool"]
            self.assertEqual("large-result", tool_messages[0]["tool_call_id"])
            self.assertEqual(shortened, tool_messages[0]["content"])
            self.assertEqual(short_result, tool_messages[1]["content"])
            self.assertEqual("refund-result", tool_messages[1]["tool_call_id"])

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
