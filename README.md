# 售后处理 Agent

这是一个以售后处理为场景的轻量 Agent Harness 项目。模型负责决定何时调用工具以及何时结束，项目代码负责提供模型入口、消息循环和工具执行边界。当前目标是先建立一条足够小、能够继续演进的主链路。

目前的执行流程是：

```text
main 接收用户输入
→ 从 MODEL_POOL 取得 ModelConfig 并创建模型客户端
→ agent_loop 将消息交给模型
→ 模型直接回答：结束本轮
→ 模型调用工具：execute_tool 解析并通过 TOOL_HANDLERS 分发
→ 工具结果写回 messages
→ 重新进入 agent_loop
```


