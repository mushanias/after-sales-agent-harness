"""保存一个会话的系统输入与只追加的动态消息历史。"""

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from compact import CompactionResult, Compactor


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
    独立管理一个会话的输入与历史，通过注入的压缩器获取并记录压缩结果。

    system_prompt、skills 单独保存，history 只包含 user、assistant 和 tool。
    写入入口分别校验消息及工具配对关系；失败时保持已有历史不变。
    压缩器选择省略范围和标记文本，Session 校验替换后的会话完整性。
    整段裁剪记录与单条工具结果的短文本分开保存，原始历史始终完整。
    完整历史只追加；build_context 应用最新压缩结果，按需生成独立上下文。
    """

    def __init__(
        self,
        system_prompt: str,
        skills: str,
        compactor: Compactor | None = None,
    ) -> None:
        """保存系统输入和可选压缩器，创建本会话独立的历史与结果记录。"""

        self._inputs = SessionInputs(system_prompt=system_prompt, skills=skills)
        if not self._inputs.system_prompt.strip():
            raise ValueError("system_prompt 不能只有空白字符")

        self._history: list[dict[str, Any]] = []
        self._pending_tool_calls: set[str] = set()
        self._compactor = compactor
        self._compaction_results: list[CompactionResult] = []
        self._shortened_tool_texts: dict[int, str] = {}

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

    @property
    def compaction_results(self) -> tuple[CompactionResult, ...]:
        """读取压缩结果记录的独立副本；只有最新结果用于当前上下文。"""

        return tuple(deepcopy(self._compaction_results))

    @property
    def shortened_tool_texts(self) -> dict[int, str]:
        """读取已保存的工具短文本副本：原始消息位置对应缩短后的正文，不执行压缩。"""

        return dict(self._shortened_tool_texts)

    def run_compaction(self) -> None:
        """组织按需压缩流程：委托压缩器计算工具短文本和历史方案，校验后统一保存。"""

        if self._compactor is None:
            return
        if self._pending_tool_calls:
            raise ValueError("工具结果尚未全部返回，不能检查压缩")

        history = self.history
        tool_results = dict(self._shortened_tool_texts)
        for index, message in enumerate(history):
            if message["role"] != "tool":
                continue
            if index not in tool_results:
                content = self._compactor.shorten_tool_text(
                    content=message["content"], history_index=index
                )
                if content is not None:
                    tool_results[index] = ToolResult(
                        tool_call_id=message["tool_call_id"], content=content
                    ).content
            if index in tool_results:
                message["content"] = tool_results[index]

        current_result = (
            deepcopy(self._compaction_results[-1])
            if self._compaction_results
            else None
        )
        result = self._compactor.plan_history_compaction(
            history=history,
            current_result=current_result,
        )
        if result is not None:
            # 可变的 Pydantic 实例也重新校验；全部成功后再记录，避免保存半个结果。
            payload = result.model_dump() if isinstance(result, CompactionResult) else result
            validated_result = CompactionResult.model_validate(payload)
            self._validate_compaction(validated_result)
            validated_result = validated_result.model_copy(deep=True)

        # 原文已经完整记录；压缩失败时不写入任何一类新结果。
        self._shortened_tool_texts = tool_results
        if result is not None:
            self._compaction_results.append(validated_result)

    def _validate_compaction(self, result: CompactionResult) -> None:
        """校验替换范围和组装后的会话完整性，不限定具体裁剪策略。"""

        if not 0 <= result.start < result.end <= len(self._history):
            raise ValueError("压缩范围必须位于完整历史内")
        current_user_index = next(
            index for index in range(len(self._history) - 1, -1, -1)
            if self._history[index]["role"] == "user"
        )
        if result.start <= current_user_index < result.end:
            raise ValueError("压缩不能替换当前用户问题")

        candidate = (
            self._history[:result.start]
            + [{"role": "assistant", "content": result.content}]
            + self._history[result.end:]
        )
        # 标记不会引入工具调用，只检查省略原文后是否仍能完整配对。
        pending_calls: set[str] = set()
        for message in candidate:
            if message["role"] == "tool":
                call_id = message["tool_call_id"]
                if call_id not in pending_calls:
                    raise ValueError("压缩后的工具结果没有对应的待返回调用")
                pending_calls.remove(call_id)
                continue
            if pending_calls:
                raise ValueError("压缩后的工具结果尚未全部返回，不能接入其他消息")
            pending_calls.update(call["id"] for call in message.get("tool_calls", []))
        if pending_calls:
            raise ValueError("压缩后的历史缺少工具结果")

    def build_context(self) -> list[dict[str, Any]]:
        """
        组装系统 prompt、skills 短目录和当前历史窗口，返回独立的模型消息列表。

        工具结果必须全部到齐，避免将无法配对的消息链发送给模型。
        每次组装都读取最新完整历史与压缩结果，组装结果不写回历史。
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
        history = self.history
        # 按原始位置替换正文，再裁剪轮次；role 和 tool_call_id 均来自原文。
        for index, content in self._shortened_tool_texts.items():
            history[index]["content"] = content
        if self._compaction_results:
            result = self._compaction_results[-1]
            # 只替换上下文副本；新追加的回复和工具结果仍来自完整历史的尾部。
            history = (
                history[:result.start]
                + [{"role": "assistant", "content": result.content}]
                + history[result.end:]
            )
        return system_messages + history

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
