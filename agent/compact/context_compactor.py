"""保存当前会话的压缩快照，并组装模型消息。"""

# 让类型标注延迟解析。它不参与压缩逻辑，主要用于减少类型标注的版本限制。
from __future__ import annotations

# 普通 copy 只复制外层；deepcopy 会连消息里面的字典、列表一起复制。
from copy import deepcopy
# 消息字典中可能有字符串、列表、工具调用等多种值，所以这里先用 Any 表示。
from typing import Any

# BaseModel 定义数据契约，ConfigDict 配置整个模型，Field 配置单个字段。
from pydantic import BaseModel, ConfigDict, Field


class CompactionSnapshot(BaseModel):
    """保存累计摘要及其覆盖终点；cut 指向第一条保留原文的消息。"""

    # extra="forbid"：出现未声明字段时直接报错，方便发现参数拼写错误。
    # frozen=True：快照创建后不能再修改，避免摘要和 cut 被偷偷改写。
    # str_strip_whitespace=True：自动去掉 summary 两侧的空白字符。
    model_config = ConfigDict(
        extra="forbid", frozen=True, str_strip_whitespace=True
    )

    # strict=True 不接受 "6"、6.0 等自动类型转换；gt=0 要求 cut 大于 0。
    cut: int = Field(gt=0, strict=True)
    # 摘要必须是真正的非空字符串；全是空格也会在去空白后校验失败。
    summary: str = Field(min_length=1, strict=True)


class ContextCompactor:
    """
    为一个会话记录摘要，读取完整历史并生成本次模型上下文。

    当前只接收已经生成的累计摘要，不负责触发压缩、调用模型或转存文件。
    每个会话使用独立实例，mes 必须始终是同一份只追加的历史列表。
    """

    def __init__(self) -> None:
        """创建当前会话的空快照列表。"""

        # 下划线表示这是类的内部状态；只允许通过本类提供的方法操作。
        # 使用列表追加而不是只保存一个值，是为了保留每次压缩的记录。
        self._snapshots: list[CompactionSnapshot] = []

    @property
    def snapshots(self) -> tuple[CompactionSnapshot, ...]:
        """提供已有快照的只读序列，保留每次压缩的覆盖记录。"""

        # @property 让调用方使用 compactor.snapshots，而不是 get_snapshots()。
        # 返回 tuple 而不是内部 list，调用方就不能 append、pop 或 clear。
        return tuple(self._snapshots)

    def record_summary(
        self,
        mes: list[dict[str, Any]],
        # 星号之后的参数只能写名字传入，例如 cut=6、summary="..."，
        # 这样不容易因为位置写反而把摘要和切点传错。
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

        # 先让 Pydantic 校验最基本的字段。失败时还没有修改内部列表。
        snapshot = CompactionSnapshot(cut=cut, summary=summary)

        # 第一次压缩从 system 消息之后开始；后续压缩从上一次 cut 继续前进。
        # 这一个变量把“第一次”和“以后每次”的判断统一到下面同一条规则里。
        previous_cut = (
            self._snapshots[-1].cut if self._snapshots else self._system_end(mes)
        )

        # 左边保证 cut 不后退，也不会覆盖开头的 system 消息；
        # 右边保证 cut 后面至少还有一条需要保留的原始消息。
        if not previous_cut < snapshot.cut < len(mes):
            raise ValueError("cut 必须向前推进，并保留当前用户轮次")

        # cut 指向“第一条保留消息”。规定它必须是 user，能让 mes[cut:]
        # 从一个完整的新轮次开始，避免上下文从半轮对话中间断开。
        if mes[snapshot.cut].get("role") != "user":
            raise ValueError("cut 必须指向保留轮次的第一条 user 消息")

        previous_message = mes[snapshot.cut - 1]
        # cut 前必须是已经结束的 assistant 回复。如果它还带 tool_calls，
        # 说明工具调用链尚未结束，此处切开会留下无法配对的工具消息。
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
            # 即使没有压缩，也不把原始 mes 直接交出去，避免调用方修改历史。
            return deepcopy(mes)

        # 摘要是累计摘要，所以只发送最新一份；旧快照只负责保留历史记录。
        snapshot = self._snapshots[-1]
        context = [
            # 星号会把切片里的每条消息逐条放入新列表。
            *mes[:self._system_end(mes)],
            # 摘要使用 assistant 身份，并明确标注“仅作参考”，不提升为 system 指令。
            {
                "role": "assistant",
                "content": f"历史摘要，仅作参考：\n{snapshot.summary}",
            },
            # cut 指向第一条保留原文，所以这里不需要 cut + 1。
            *mes[snapshot.cut:],
        ]
        # 工作上下文中的嵌套字典也独立，后续处理不会连带改写原始历史。
        return deepcopy(context)

    @staticmethod
    def _system_end(mes: list[dict[str, Any]]) -> int:
        """找到开头连续 system 消息的结束位置，这些固定提示始终保留。"""

        # @staticmethod 表示这个方法不需要读取 self，只是逻辑上属于这个类。
        # enumerate 同时给出索引和消息；遇到第一条非 system 消息时，
        # 它的索引正好就是 mes[:index] 的结束位置。
        for index, message in enumerate(mes):
            if message.get("role") != "system":
                return index
        # 如果列表里全是 system 消息，结束位置就是列表长度。
        return len(mes)
