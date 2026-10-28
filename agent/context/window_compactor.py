"""按需读取原文并维护模型工作消息，使用文本截短和轮次裁剪控制上下文。"""

import json
from copy import deepcopy
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from session import Session


class WindowContextProjector(BaseModel):
    """
    保留首轮和最近几轮，用说明消息替代中间的完整轮次。

    max_chars 是动态历史工作窗口的字符预算，不是精确 token 数；
    keep_recent_turns 包含刚追加的当前用户轮次。参数由 Pydantic 校验。
    单条工具结果超过 max_tool_result_chars 时，保留首尾并标明中间省略。
    一个实例服务一个会话，内部保存工作消息和原文处理进度，均不交给 Session。
    """

    max_chars: int = Field(default=20_000, gt=0)
    keep_recent_turns: int = Field(default=3, ge=1)
    # 给省略说明留出空间；预算包含首尾文本和说明本身。
    max_tool_result_chars: int = Field(default=4_000, ge=256)

    _messages: list[dict[str, Any]] = PrivateAttr(default_factory=list)
    _history_end: int = PrivateAttr(default=0)

    def get_history(self, session: Session) -> list[dict[str, Any]]:
        """由投影器取得完整原文副本，读取方式不进入 Loop。"""

        return session.history

    def build_messages(self, session: Session) -> list[dict[str, Any]]:
        """取得完整原文副本，再交给本策略处理。"""

        return self.compact_history(self.get_history(session))

    def compact_history(self, history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """从完整原文副本接入新增消息；加工成功后才保存工作状态。"""

        messages = self._shorten_tool_results(self._messages + history[self._history_end:])
        messages = self._crop_history(history, messages)

        # 本次加工失败时不推进游标；重试仍能接入尚未处理的新消息。
        self._messages = messages
        self._history_end = len(history)
        return deepcopy(messages)

    def _shorten_tool_results(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """只改副本中的工具正文；已有短文本自然满足长度限制，无需额外映射。"""

        messages = deepcopy(messages)
        for message in messages:
            if message["role"] == "tool":
                message["content"] = self._shorten_tool_text(message["content"])
        return messages

    def _shorten_tool_text(self, content: str) -> str:
        """保留正文首尾和省略说明；工具角色、调用 ID 和参数保持原样。"""

        if len(content) <= self.max_tool_result_chars:
            return content
        marker = (
            f"\n[工具结果已截短，原文共 {len(content)} 字符，中间内容已省略。"
            "完整原文仍在本会话 Session.history 的内存记录中。"
            "归档读取尚未接入；不要推测省略内容，也不要重新执行业务操作恢复历史。]\n"
        )
        keep_chars = self.max_tool_result_chars - len(marker)
        head_chars = keep_chars // 2
        tail_chars = keep_chars - head_chars
        return content[:head_chars] + marker + content[-tail_chars:]

    def _crop_history(
        self,
        history: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """在新用户轮次开始时，必要则从原文重建窗口，避免叠加旧省略标记。"""

        if not history or history[-1]["role"] != "user":
            return messages
        current_chars = self._estimate_chars(messages)
        if current_chars <= self.max_chars:
            return messages

        turn_starts = [
            index for index, message in enumerate(history)
            if message["role"] == "user"
        ]
        if len(turn_starts) <= self.keep_recent_turns + 1:
            return messages

        # 两端都落在 user 消息之前，完整工具调用和结果会一起保留或省略。
        start = turn_starts[1]
        end = turn_starts[-self.keep_recent_turns]
        marker = {
            "role": "assistant",
            "content": (
                f"历史压缩标记，仅说明上下文省略情况：已省略 {end - start} 条消息，"
                f"原文范围为 [{start}, {end})。完整原文仍保存在本会话的 "
                f"Session.history[{start}:{end}] 内存记录中。"
                "文件归档和读取工具尚未接入。"
                "若当前问题依赖省略的信息，应说明缺失并向用户确认；"
                "不要推测原文，也不要重新执行业务操作来恢复历史。"
            ),
        }
        candidate = self._shorten_tool_results(history[:start] + [marker] + history[end:])
        if self._estimate_chars(candidate) >= current_chars:
            return messages
        return candidate

    @staticmethod
    def _estimate_chars(messages: list[dict[str, Any]]) -> int:
        """粗估动态消息序列化后的字符数；以后可在此替换 token 估算方式。"""

        return len(json.dumps(messages, ensure_ascii=False, default=str))
