"""售后 Agent 的系统提示、工具执行与核心循环。"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from hooks import trigger_hooks
from knowledge import rules, skills
from middleware import approval_middleware
from model import ModelConfig
from tool import TOOL_HANDLERS, TOOLS


SYSTEM_PROMPT = f"""你是声途 HiFi 店的售后处理 Agent。当前日期是 {date.today().isoformat()}。

你处理取消订单、物流异常、七天无理由退货、质量问题以及错发漏发咨询，但当前只有
查询订单和发起七天无理由退款申请两项业务工具。

处理规则：
1. 需要判断具体订单时，用户未提供订单号就先询问；取得订单号后必须先使用
   lookup_order 查询，不能把用户口述当作订单系统事实。
2. 先识别售后类型，再根据工具返回的事实和下方业务知识判断。信息不足时只追问
   影响当前判断的事实，不要猜测。
3. 只有订单明确符合七天无理由规则、用户明确要求提交申请时，才使用
   request_refund。质量问题、物流拦截、换货和维修不能使用该工具代办。
4. 知识库说明某项业务可以办理，不代表你已经执行。没有对应工具时，只能说明规则、
   收集所需信息并告知需要人工处理，不得声称已经拦截、检测、换货、维修或补发。
5. 订单工具结果优先于用户口述；法律规则优先于商家店规；案例只用于帮助理解，
   不能替代当前订单的事实判断。
6. 只能根据工具结果描述处理状态，不要编造订单、退款结果或到账时间。
7. 当请求需要多个步骤或处理多个订单时，先使用 todo_write 建立完整计划，并随着
   处理进度更新步骤状态；简单查询不需要创建 Todo。

业务知识：
## 法律规则与商家规则

{rules.load_rules()}

## 售后处理 Skills

{skills.load_skills()}
"""

def execute_tool(tool_call: Any) -> str:
    """
    在 Loop 允许执行工具后，解析参数并调用已注册的处理器。

    调用方式：
        execute_tool(tool_call)

    输入字段：
        tool_call：模型 SDK 返回的工具调用对象，必须包含工具名和 JSON 参数。

    输出字段：
        JSON 字符串；成功时包含工具实现返回的字段，失败时包含 ok、error 和
        message，供下一轮模型响应使用。
    """

    tool_name = tool_call.function.name

    try:
        arguments = json.loads(tool_call.function.arguments)
    except (json.JSONDecodeError, TypeError) as error:
        result = {
            "ok": False,
            "error": "INVALID_TOOL_ARGUMENTS",
            "message": str(error),
        }
        return json.dumps(result, ensure_ascii=False)

    if not isinstance(arguments, dict):
        result = {
            "ok": False,
            "error": "INVALID_TOOL_ARGUMENTS",
            "message": "工具参数必须是 JSON 对象",
        }
        return json.dumps(result, ensure_ascii=False)

    handler = TOOL_HANDLERS.get(tool_name)

    if handler is None:
        result = {
            "ok": False,
            "error": "UNKNOWN_TOOL",
            "message": f"没有注册工具 {tool_name}",
        }
        return json.dumps(result, ensure_ascii=False)

    try:
        result = handler(**arguments)
    except (TypeError, ValueError) as error:
        result = {
            "ok": False,
            "error": "TOOL_EXECUTION_ERROR",
            "message": str(error),
        }

    return json.dumps(result, ensure_ascii=False)


def agent_loop(
    client: Any,
    model: ModelConfig,
    messages: list[dict[str, Any]],
) -> str | None:
    """持续执行模型请求的工具，直到模型决定直接回复。"""

    while True:
        response = client.chat.completions.create(
            model=model.model_id,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}, *messages],
            tools=TOOLS,
            max_tokens=8000,
        )
        response_message = response.choices[0].message
        trigger_hooks("PostModelResponse", response_message)
        messages.append(response_message.model_dump(exclude_none=True))

        tool_calls = response_message.tool_calls or []
        if not tool_calls:
            return response_message.content

        for tool_call in tool_calls:
            trigger_hooks("PreToolUse", tool_call)
            tool_result = approval_middleware(
                tool_call,
                execute_tool,
            )
            post_hook_result = trigger_hooks("PostToolUse", tool_call, tool_result)
            if post_hook_result is not None:
                tool_result = f"{tool_result}\n{post_hook_result}"
            #     这里保留边界，后面记得改
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )
