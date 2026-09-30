"""保存一个会话的系统输入与只追加的动态消息历史。"""

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class SessionInputs(BaseModel):
    """保存系统 prompt 和 skills 短目录；短目录允许为空。"""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)

    system_prompt: str = Field(min_length=1)
    skills: str


class UserMessage(BaseModel):
    """保存开启一轮对话的用户文本。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    role: Literal["user"] = "user"
    content: str = Field(min_length=1)


class ToolCall(BaseModel):
    """校验工具调用的关联 ID，其余模型字段原样保留。"""

    model_config = ConfigDict(extra="allow", strict=True)

    id: str = Field(min_length=1)


class AssistantMessage(BaseModel):
    """保存模型回复或工具调用，也保留 SDK 提供的额外字段。"""

    model_config = ConfigDict(extra="allow", strict=True)

    role: Literal["assistant"]
    content: str | None = None
    tool_calls: list[ToolCall] | None = None


class ToolResult(BaseModel):
    """保存某次工具调用的文本结果；空结果也是合法结果。"""

    model_config = ConfigDict(extra="forbid", strict=True)

    role: Literal["tool"] = "tool"
    tool_call_id: str = Field(min_length=1)
    content: str


class Session:
    """
    独立管理一个会话的输入与历史，不调用模型、执行工具或压缩历史。

    system_prompt、skills 单独保存，history 只包含 user、assistant 和 tool。
    写入入口分别校验消息及工具配对关系；失败时保持已有历史不变。
    当前仅保存在内存中，build_context 按需生成独立的模型上下文。
    """

    def __init__(self, system_prompt: str, skills: str) -> None:
        """校验系统输入，并为本会话创建独立的历史与待返回工具集合。"""

        self._inputs = SessionInputs(system_prompt=system_prompt, skills=skills)
        if not self._inputs.system_prompt.strip():
            raise ValueError("system_prompt 不能只有空白字符")

        self._history: list[dict[str, Any]] = []
        self._pending_tool_calls: set[str] = set()

    @property
    def system_prompt(self) -> str:
        """读取本会话的系统 prompt。"""

        return self._inputs.system_prompt

    @property
    def skills(self) -> str:
        """读取本会话的 skills 短目录。"""

        return self._inputs.skills

    @property
    def history(self) -> list[dict[str, Any]]:
        """读取完整动态历史的深拷贝，避免调用方修改内部记录。"""

        return deepcopy(self._history)

    def build_context(self) -> list[dict[str, Any]]:
        """
        组装系统 prompt、skills 短目录和最新历史，返回独立的模型消息列表。

        工具结果必须全部到齐，避免将无法配对的消息链发送给模型。
        每次组装都读取当前历史，组装结果不写回历史。
        """

        if self._pending_tool_calls:
            raise ValueError("工具结果尚未全部返回，不能组装模型上下文")

        system_messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "system",
                "content": f"可用 Skills 短目录：\n{self.skills}",
            },
        ]
        # history 返回深拷贝；后续筛选或压缩上下文不会连带改写原始历史。
        return system_messages + self.history

    def add_user(self, content: str) -> None:
        """上一轮有最终回复后，记录新的用户输入。"""

        message = UserMessage(content=content)
        if not message.content.strip():
            raise ValueError("用户消息不能只有空白字符")
        if self._history and (
            self._history[-1]["role"] != "assistant" or self._pending_tool_calls
        ):
            raise ValueError("上一轮尚未得到最终回复，不能追加新的用户消息")

        self._history.append(message.model_dump())

    def add_assistant(self, reply: dict[str, Any]) -> None:
        """
        记录模型回复；reply 由 SDK 消息的 model_dump(exclude_none=True) 提供。

        带工具调用的回复会登记待返回 ID；全部工具结果到齐后才能记录下一次回复。
        这里只保存工具调用，不解析工具参数，也不执行工具。
        """

        message = AssistantMessage.model_validate(reply)
        if not self._history or self._history[-1]["role"] == "assistant":
            raise ValueError("模型回复必须接在用户消息或工具结果之后")
        if self._pending_tool_calls:
            raise ValueError("还有工具结果未返回，不能追加模型回复")

        tool_call_ids = [call.id for call in message.tool_calls or []]
        if len(tool_call_ids) != len(set(tool_call_ids)):
            raise ValueError("同一次模型回复中的工具调用 ID 不能重复")

        # 校验全部通过后再追加；深拷贝也隔离调用方持有的嵌套工具参数。
        self._history.append(deepcopy(message.model_dump(exclude_none=True)))
        self._pending_tool_calls.update(tool_call_ids)

    def add_tool_result(self, tool_call_id: str, content: str) -> None:
        """记录待返回工具的结果；拒绝无法匹配或已经返回过的 ID。"""

        message = ToolResult(tool_call_id=tool_call_id, content=content)
        if message.tool_call_id not in self._pending_tool_calls:
            raise ValueError("tool_call_id 没有对应的待返回工具调用")

        self._history.append(message.model_dump())
        self._pending_tool_calls.remove(message.tool_call_id)
