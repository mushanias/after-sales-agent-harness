"""裁剪旧轮次并缩短过长工具文本；完整原文由 Session 保留，不调用模型。"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field

from .contracts import CompactionResult


class WindowCompactor(BaseModel):
    """
    保留首轮和最近几轮，用说明消息替代中间的完整轮次。

    max_chars 是动态历史工作窗口的字符预算，不是精确 token 数；
    keep_recent_turns 包含刚追加的当前用户轮次。参数由 Pydantic 校验。
    单条工具结果超过 max_tool_result_chars 时，保留首尾并标明中间省略。
    """

    max_chars: int = Field(default=20_000, gt=0)
    keep_recent_turns: int = Field(default=3, ge=1)
    # 给省略说明留出空间；预算包含首尾文本和说明本身。
    max_tool_result_chars: int = Field(default=4_000, ge=256)

    def compact_tool_result(self, content: str, history_index: int) -> str | None:
        """只缩短工具正文，返回首尾片段和说明；工具角色与调用 ID 由 Session 保留。"""

        if len(content) <= self.max_tool_result_chars:
            return None
        marker = (
            f"\n[工具结果已截短，原文共 {len(content)} 字符，中间内容已省略。"
            f"完整原文仍在本会话 Session.history[{history_index}] 的内存记录中。"
            "归档读取尚未接入；不要推测省略内容，也不要重新执行业务操作恢复历史。]\n"
        )
        keep_chars = self.max_tool_result_chars - len(marker)
        if keep_chars < 2:
            raise ValueError("单条工具结果预算不足以容纳省略说明")
        head_chars = keep_chars // 2
        tail_chars = keep_chars - head_chars
        return content[:head_chars] + marker + content[-tail_chars:]

    def compact_if_needed(
        self,
        history: list[dict[str, Any]],
        current_result: CompactionResult | None,
    ) -> CompactionResult | None:
        """检查当前工作窗口，必要时返回覆盖原始历史中段的完整替换结果。"""

        # 首版只处理新用户轮次开始时的旧历史，不在单轮工具链中间裁剪。
        if not history or history[-1].get("role") != "user":
            return None

        window = history
        if current_result is not None:
            window = (
                history[:current_result.start]
                + [{"role": "assistant", "content": current_result.content}]
                + history[current_result.end:]
            )
        current_chars = self._estimate_chars(window)
        if current_chars <= self.max_chars:
            return None

        turn_starts = [
            index for index, message in enumerate(history)
            if message.get("role") == "user"
        ]
        if len(turn_starts) <= self.keep_recent_turns + 1:
            return None

        # 两端都落在 user 消息之前，完整工具调用和结果会一起保留或省略。
        start = turn_starts[1]
        end = turn_starts[-self.keep_recent_turns]
        if (
            current_result is not None
            and start == current_result.start
            and end <= current_result.end
        ):
            return None

        result = CompactionResult(
            start=start,
            end=end,
            content=(
                f"历史压缩标记，仅说明上下文省略情况：已省略 {end - start} 条消息，"
                f"原文范围为 [{start}, {end})。完整原文仍保存在本会话的 "
                f"Session.history[{start}:{end}] 内存记录中。"
                "文件归档和读取工具尚未接入。"
                "若当前问题依赖省略的信息，应说明缺失并向用户确认；"
                "不要推测原文，也不要重新执行业务操作来恢复历史。"
            ),
            archive_path=None,
        )
        candidate = (
            history[:start]
            + [{"role": "assistant", "content": result.content}]
            + history[end:]
        )
        if self._estimate_chars(candidate) >= current_chars:
            return None
        return result

    @staticmethod
    def _estimate_chars(messages: list[dict[str, Any]]) -> int:
        """粗估动态消息序列化后的字符数；以后可在此替换估算方式。"""

        return len(json.dumps(messages, ensure_ascii=False, default=str))
