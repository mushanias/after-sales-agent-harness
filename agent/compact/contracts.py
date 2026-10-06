"""Session 与压缩器之间的数据和方法契约；具体压缩策略另行实现。"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CompactionResult(BaseModel):
    """
    记录原始 history 的替换范围、替代消息，以及供后续工具使用的归档路径。

    范围采用 [start, end)，对应完整 history 的消息位置；包含 start，不包含 end。
    archive_path 仅是连接点；当前不检查文件存在，也不实现归档读写。
    """

    start: int = Field(ge=0)
    end: int = Field(gt=0)
    messages: list[dict[str, Any]] = Field(min_length=1)
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
    """约定压缩器的一个入口；是否压缩以及如何压缩由具体策略决定。"""

    def compact_if_needed(
        self,
        history: list[dict[str, Any]],
        current_result: CompactionResult | None,
    ) -> CompactionResult | None:
        """
        接收完整动态历史和上一次结果的副本，返回新的完整替换结果。

        history 不包含系统 prompt 和 skills。返回 None 表示保持原状态；
        结果由 Session 保存，本契约不实现摘要生成或模型调用。
        """

        ...
