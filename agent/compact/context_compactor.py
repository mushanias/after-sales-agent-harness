"""保存当前会话的压缩快照，并组装模型消息。"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CompactionSnapshot(BaseModel):
    """保存累计摘要及其覆盖终点；cut 指向第一条保留原文的消息。"""

    model_config = ConfigDict(
        extra="forbid", frozen=True, str_strip_whitespace=True
    )

    cut: int = Field(gt=0, strict=True)
    summary: str = Field(min_length=1, strict=True)


class ContextCompactor:
    """
    为一个会话记录摘要，读取完整历史并生成本次模型上下文。

    当前只接收已经生成的累计摘要，不负责触发压缩、调用模型或转存文件。
    每个会话使用独立实例，mes 必须始终是同一份只追加的历史列表。
    """

    def __init__(self) -> None:
        """创建当前会话的空快照列表。"""

        self._snapshots: list[CompactionSnapshot] = []

    @property
    def snapshots(self) -> tuple[CompactionSnapshot, ...]:
        """提供已有快照的只读序列，保留每次压缩的覆盖记录。"""

        return tuple(self._snapshots)

    def record_summary(
        self,
        mes: list[dict[str, Any]],
        *,
        cut: int,
        summary: str,
    ) -> CompactionSnapshot:
        """
        校验后追加一份累计摘要，失败时保持已有快照不变。

        summary 必须覆盖开头 system 消息之后、cut 之前的全部历史。
        再次记录时，调用方需要提供“旧摘要 + 新覆盖原文”的累计摘要。
        cut 必须指向下一轮 user 消息，其前一轮已经得到最终回复。
        """

        snapshot = CompactionSnapshot(cut=cut, summary=summary)
        previous_cut = (
            self._snapshots[-1].cut if self._snapshots else self._system_end(mes)
        )
        if not previous_cut < snapshot.cut < len(mes):
            raise ValueError("cut 必须向前推进，并保留当前用户轮次")
        if mes[snapshot.cut].get("role") != "user":
            raise ValueError("cut 必须指向保留轮次的第一条 user 消息")

        previous_message = mes[snapshot.cut - 1]
        if (
            previous_message.get("role") != "assistant"
            or previous_message.get("tool_calls")
        ):
            raise ValueError("cut 前一轮必须已有不含工具调用的最终 assistant 回复")

        # 摘要和切点一起生效，避免校验失败时原文已被排除、摘要却不可用。
        self._snapshots.append(snapshot)
        return snapshot

    def prepare(self, mes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """返回 system + 最新累计摘要 + mes[cut:]；没有摘要时返回完整历史副本。"""

        if not self._snapshots:
            return deepcopy(mes)

        snapshot = self._snapshots[-1]
        context = [
            *mes[:self._system_end(mes)],
            {
                "role": "assistant",
                "content": f"历史摘要，仅作参考：\n{snapshot.summary}",
            },
            *mes[snapshot.cut:],
        ]
        # 工作上下文中的嵌套字典也独立，后续处理不会连带改写原始历史。
        return deepcopy(context)

    @staticmethod
    def _system_end(mes: list[dict[str, Any]]) -> int:
        """找到开头连续 system 消息的结束位置，这些固定提示始终保留。"""

        for index, message in enumerate(mes):
            if message.get("role") != "system":
                return index
        return len(mes)
