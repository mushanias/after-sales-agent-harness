



def agent_loop(task:str) -> str | None:
    """持续执行模型请求的工具，直到模型决定直接回复。"""
    messages = [{"role": "user", "content": task}]
    for _ in range(30):
        response = client.chat.completions.create(
            model=model.model_id,
            messages=messages,
            tools=SUB_TOOLS,
            max_tokens=8000,
        )
        response_message = response.choices[0].message

        messages.append({"role": "assistant", "content": response_message.model_dump(exclude_none=True)})

        tool_calls = response_message.tool_calls or []
        if not tool_calls:
            return "意义不明的指令，请检查是否有这个工具"

        for tool_call in tool_calls:
            tool_result = approval_middleware(
                tool_call,
                execute_tool,
            )
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_result,
                }
            )