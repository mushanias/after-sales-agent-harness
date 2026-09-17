"""当前会话 Todo 计划的模型声明与执行实现。"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator


class TodoStatus(str, Enum):
    """定义一项 Todo 在当前计划中的执行状态。"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class TodoItem(BaseModel):
    """描述模型写入当前计划的一项任务。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    content: str
    status: TodoStatus

    @field_validator("content")
    @classmethod
    def normalize_content(cls, content: str) -> str:
        """去除任务内容首尾空白，并拒绝空任务。"""

        normalized_content = content.strip()
        if not normalized_content:
            raise ValueError("任务内容不能为空")
        return normalized_content


class TodoUpdate(BaseModel):
    """校验一次 todo_write 提交的完整计划。"""

    model_config = ConfigDict(extra="forbid")

    todos: list[TodoItem]

    @field_validator("todos")
    @classmethod
    def validate_todo_count(cls, todos: list[TodoItem]) -> list[TodoItem]:
        """限制单次计划大小，避免 Todo 本身挤占过多上下文。"""

        if len(todos) > 20:
            raise ValueError("Todo 最多包含 20 项")
        return todos

    @model_validator(mode="after")
    def validate_in_progress_count(self) -> "TodoUpdate":
        """保证当前计划同一时间最多只有一项正在执行。"""

        in_progress_count = sum(
            todo.status is TodoStatus.IN_PROGRESS for todo in self.todos
        )
        if in_progress_count > 1:
            raise ValueError("同一时间只能有一项 Todo 处于 in_progress")
        return self


TODO_WRITE_TOOL = {
    "type": "function",
    "function": {
        "name": "todo_write",
        "description": (
            "创建或更新当前会话的完整任务计划。这个工具只记录计划状态，"
            "不会查询订单或执行退款。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "todos": {
                    "type": "array",
                    "description": "当前完整 Todo 列表；传入空列表表示清空计划。",
                    "maxItems": 20,
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {
                                "type": "string",
                                "minLength": 1,
                                "description": "需要完成的具体步骤。",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["pending", "in_progress", "completed"],
                                "description": "该步骤当前的执行状态。",
                            },
                        },
                        "required": ["content", "status"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["todos"],
            "additionalProperties": False,
        },
    },
}


_CURRENT_TODOS: list[TodoItem] = []


def todo_write(todos: list[dict[str, Any]]) -> dict[str, Any]:
    """
    用模型提交的完整列表替换当前会话的 Todo 计划。

    调用方式：
        todo_write(
            todos=[
                {"content": "查询订单 1001", "status": "in_progress"},
                {"content": "判断退款条件", "status": "pending"},
            ]
        )

    输入字段：
        todos：当前完整计划。每项包含非空 content，以及 pending、
        in_progress、completed 三种状态之一。

    输出字段：
        ok：是否成功更新当前计划。
        todos：更新成功后返回规范化的完整计划。
        error：失败时的稳定错误代码。
        message：失败原因，供模型修正计划后重新提交。

    当前边界：
        Todo 只保存在当前 Python 进程的内存中，不持久化，也不代表订单或
        退款的真实状态。提交内容会先完整校验，校验失败时保留原计划不变。
    """

    try:
        update = TodoUpdate(todos=todos)
    except ValidationError as error:
        first_error = error.errors(include_url=False)[0]
        return {
            "ok": False,
            "error": "INVALID_TODOS",
            "message": first_error["msg"],
        }

    # 先完成整份计划的校验再替换，避免失败请求留下半更新状态。
    _CURRENT_TODOS[:] = update.todos

    return {
        "ok": True,
        "todos": [todo.model_dump(mode="json") for todo in _CURRENT_TODOS],
    }

