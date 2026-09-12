"""最小 Agent Loop 的单元测试。"""

from types import SimpleNamespace
import unittest

from main import agent_loop, lookup_order


class FakeMessages:
    """按顺序返回预设响应，并记录模型调用参数。"""

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return next(self.responses)


class FakeClient:
    """提供与 Anthropic 客户端一致的 messages 入口。"""

    def __init__(self, responses):
        self.messages = FakeMessages(responses)


class AgentLoopTests(unittest.TestCase):
    """验证工具结果会回到模型，并由模型决定何时停止。"""

    def test_tool_result_is_fed_back_before_loop_stops(self):
        tool_call = SimpleNamespace(
            type="tool_use",
            name="lookup_order",
            id="tool-1",
            input={"order_id": "A1001"},
        )
        final_text = SimpleNamespace(type="text", text="订单 A1001 已签收。")
        client = FakeClient(
            [
                SimpleNamespace(content=[tool_call]),
                SimpleNamespace(content=[final_text]),
            ]
        )
        messages = [{"role": "user", "content": "查询 A1001"}]

        agent_loop(client, "test-model", messages)

        self.assertEqual(2, len(client.messages.calls))
        self.assertEqual(
            ["user", "assistant", "user", "assistant"],
            [message["role"] for message in messages],
        )
        tool_result = messages[2]["content"][0]
        self.assertEqual("tool-1", tool_result["tool_use_id"])
        self.assertIn('"found": true', tool_result["content"])

    def test_loop_stops_without_adding_empty_tool_result(self):
        final_text = SimpleNamespace(type="text", text="请提供订单号。")
        client = FakeClient([SimpleNamespace(content=[final_text])])
        messages = [{"role": "user", "content": "我要售后"}]

        agent_loop(client, "test-model", messages)

        self.assertEqual(
            ["user", "assistant"],
            [message["role"] for message in messages],
        )

    def test_lookup_order_returns_not_found(self):
        result = lookup_order("UNKNOWN")

        self.assertIn('"found": false', result)
        self.assertIn('"order_id": "UNKNOWN"', result)


if __name__ == "__main__":
    unittest.main()
