"""最小 Agent Loop 的单元测试。"""

from types import SimpleNamespace
import unittest

from main import agent_loop, lookup_order
from model_pool import DEFAULT_MODEL, MODEL_POOL, ModelConfig


class FakeCompletions:
    """按顺序返回预设响应，并记录模型调用参数。"""

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


class FakeClient:
    """提供与 OpenAI 兼容客户端一致的调用入口。"""

    def __init__(self, responses):
        self.chat = SimpleNamespace(completions=FakeCompletions(responses))


class AgentLoopTests(unittest.TestCase):
    """验证工具结果会回到模型，并由模型决定何时停止。"""

    def test_tool_result_is_fed_back_before_loop_stops(self):
        tool_call = SimpleNamespace(
            id="tool-1",
            function=SimpleNamespace(
                name="lookup_order",
                arguments='{"order_id": "A1001"}',
            ),
        )
        client = FakeClient(
            [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content=None,
                                tool_calls=[tool_call],
                            )
                        )
                    ]
                ),
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content="订单 A1001 已签收。",
                                tool_calls=None,
                            )
                        )
                    ]
                ),
            ]
        )
        messages = [{"role": "user", "content": "查询 A1001"}]

        agent_loop(client, MODEL_POOL[DEFAULT_MODEL], messages)

        self.assertEqual(2, len(client.chat.completions.calls))
        self.assertEqual(
            "deepseek-v4-pro",
            client.chat.completions.calls[0]["model"],
        )
        self.assertEqual(
            ["user", "assistant", "tool", "assistant"],
            [message["role"] for message in messages],
        )
        tool_result = messages[2]
        self.assertEqual("tool-1", tool_result["tool_call_id"])
        self.assertIn('"found": true', tool_result["content"])

    def test_loop_stops_without_adding_empty_tool_result(self):
        client = FakeClient(
            [
                SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(
                                content="请提供订单号。",
                                tool_calls=None,
                            )
                        )
                    ]
                )
            ]
        )
        messages = [{"role": "user", "content": "我要售后"}]

        agent_loop(client, MODEL_POOL[DEFAULT_MODEL], messages)

        self.assertEqual(
            ["user", "assistant"],
            [message["role"] for message in messages],
        )

    def test_lookup_order_returns_not_found(self):
        result = lookup_order("UNKNOWN")

        self.assertIn('"found": false', result)
        self.assertIn('"order_id": "UNKNOWN"', result)

    def test_model_pool_contains_one_typed_model(self):
        self.assertEqual(["deepseek-v4-pro"], list(MODEL_POOL))
        self.assertIsInstance(MODEL_POOL[DEFAULT_MODEL], ModelConfig)
        self.assertEqual("DEEPSEEK_API_KEY", MODEL_POOL[DEFAULT_MODEL].api_key_env)


if __name__ == "__main__":
    unittest.main()
