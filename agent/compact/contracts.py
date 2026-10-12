"""Session 与压缩器之间的数据和方法契约；具体压缩策略另行实现。"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field, model_validator


class CompactionResult(BaseModel):
    """
    记录原始 history 的省略范围、标记文本，以及供后续工具使用的归档路径。

    范围采用 [start, end)，对应完整 history 的消息位置；包含 start，不包含 end。
    archive_path 仅是连接点；当前不检查文件存在，也不实现归档读写。
    """

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    content: str = Field(min_length=1)
    archive_path: str | None = Field(
        default=None,
        min_length=1,
        description="归档文件的路径，预留给后续读取工具；不代表文件已经创建。",
    )

    @model_validator(mode="after")
    def validate_range(self) -> CompactionResult:
        """要求替换范围包含至少一条原始消息。"""

        if self.end <= self.start:
            raise ValueError("end 必须大于 start")
        return self


class Compactor(Protocol):
    """声明压缩器计算工具短文本与历史裁剪方案的方法契约，不提供默认实现。"""
#这里用Protocol声明方便拓展
    def shorten_tool_text(self, content: str, history_index: int) -> str | None:
        """接收单条原始工具文本及其历史位置，返回缩短文本；None 表示保留原文。"""

        ...

    def plan_history_compaction(
        self,
        history: list[dict[str, Any]],
        current_result: CompactionResult | None,
    ) -> CompactionResult | None:
        """
        接收动态历史和上一次结果的副本，计算并返回新的完整历史裁剪方案。

        history 保持原始消息位置，过长工具文本已替换为缩短版本，
        不包含系统 prompt 和 skills。返回 None 表示保持原状态；
        结果由 Session 保存，本契约不实现摘要生成或模型调用。
        """

        ...
