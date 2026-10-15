"""Session 与压缩器之间的数据和方法契约；具体压缩策略另行实现。"""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CompactionResult(BaseModel):
    """
    记录原始 history 的省略范围、标记文本，以及供后续工具使用的归档路径。

    范围采用 [start, end)，对应完整 history 的消息位置；包含 start，不包含 end。
    archive_path 仅是连接点；当前不检查文件存在，也不实现归档读写。
    """

    model_config = ConfigDict(strict=True, revalidate_instances="always")

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


class CompactionSnapshot(BaseModel):
    """一次压缩所需的独立数据副本；history 始终是完整原文，位置不变。"""

    history: list[dict[str, Any]]
    shortened_tool_texts: dict[int, str] = Field(default_factory=dict)
    current_result: CompactionResult | None = None


class CompactionOutput(BaseModel):
    """
    一次压缩的完整工具短文本映射，以及可选的新历史裁剪结果。

    shortened_tool_texts 包含需要继续保留的旧记录；history_result 为 None
    表示沿用此前的历史裁剪结果。两类结果交给 Session 一起校验、保存。
    """

    # 结果可能在创建后被修改，进入 Session 时仍按字段契约检查一次。
    model_config = ConfigDict(strict=True, revalidate_instances="always")

    shortened_tool_texts: dict[int, str] = Field(default_factory=dict)
    history_result: CompactionResult | None = None


class Compactor(Protocol):
    """调用方只提供快照、接收结果；处理顺序和压缩算法由实现类决定。"""

    def compact(self, snapshot: CompactionSnapshot) -> CompactionOutput:
        """计算一次压缩结果，不持有或修改 Session。"""

        ...
