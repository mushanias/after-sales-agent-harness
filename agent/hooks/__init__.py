"""Agent Loop 的 Hook 注册入口。"""

from .tool_call_observer import observe_tool_calls


AFTER_MODEL_RESPONSE_HOOKS = [observe_tool_calls]

__all__ = ["AFTER_MODEL_RESPONSE_HOOKS"]
