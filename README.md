# 万物皆插件
> 一个从售后业务出发、由模型负责决策、由代码守住边界的轻量 Agent Harness。


- `main` 只负责选择模型、创建客户端和组装运行环境。
- `agent_loop` 只负责模型调用、消息追加、停止判断和工具结果回填。
- Tool 提供事实查询与业务操作。
- Skill 提供按需加载的政策规则和处理指导。
- Middleware 决定工具是否允许执行。
- Hook 观察模型与工具调用，并提供必要提醒。
- Subagent 使用独立消息列表处理子任务，只把最终结果交还父 Agent。


## 核心原则

### 模型负责判断，代码负责事实

模型可以决定查询哪个订单、加载哪项政策、是否需要委派子任务，但不能编造订单、退款状态或工具执行结果。订单事实来自 SQLite，政策与处理指导来自 Skill，产生业务影响的操作必须经过权限中间件。

### 知识和事实分开

```text
knowledge/
├── facts/       # 订单、物流、退款状态等既定事实
└── skill/
    ├── policy/  # 退换政策、运费规则等业务规则
    └── skills/  # 查询、追问、判断和执行的处理指导
```

事实通过工具进入模型上下文，Loop 不直接读取数据库。Skill 在导入时扫描 `SKILL.md` 元数据，初始上下文只提供短目录；模型确认需要某项知识后，再调用 `load_skill` 加载全文。

### 上下文是一种有限资源

主对话不需要保存每次探索产生的全部中间信息。父 Agent 可以通过 `task` 委派一项明确任务；Subagent 从新的 `messages` 开始，复用现有客户端、模型和基础工具，完成后只返回最终文本。

当前只支持一层同步委派。子 Agent 不拥有 `task`，因此不能继续创建下一层子任务。

## 调用链

```text
main 接收用户输入
→ 创建模型客户端并配置运行时工具
→ build_context 组装系统提示与 Skill 短目录
→ agent_loop 把 messages 和工具声明交给模型
→ 模型直接回答：结束本轮
→ 模型调用工具：权限中间件检查后由 execute_tool 分发
→ 工具结果写回 messages
→ 再次调用模型
```

Subagent 作为一个普通工具进入父循环：

```text
父 Agent 调用 task
→ task 文本成为子消息列表的第一条用户消息
→ 子 Agent 使用基础工具完成任务
→ 子消息列表随任务结束丢弃
→ 最终文本作为 task 的工具结果返回父 Agent
```

## 工具注册

工具分为两个入口：

- `TOOLS` 是提供给模型的 JSON Schema，说明工具名称、用途和参数。
- `TOOL_HANDLERS` 是程序侧函数表，负责执行模型选中的工具。

两者通过工具名关联。`execute_tool` 只负责解析模型参数、查找 handler、执行并序列化结果。

普通工具在模块导入时即可注册。Subagent 还需要运行时创建的 `client` 和 `model`，因此由 `configure_tools` 在程序启动时完成绑定。模型仍然只需要提供 `task` 这一项业务参数。

## 当前能力

- 查询订单事实。
- 按需加载售后政策和处理 Skill。
- 创建与更新当前任务的 Todo。
- 经人工确认后发起退款申请。
- 通过 Hooks 观察 Loop 轮次和工具调用。
- 将独立任务委派给一次性 Subagent。
- 使用本地评估用例检查售后回答。

## 当前边界

这是一个同步、单进程、单模型的 CLI Agent。当前没有实现异步执行、并发 Subagent、持久会话、长期记忆、上下文压缩、模型重试和完整链路监控。这些能力只有在真实业务规模暴露需求后才值得加入。

## 运行

安装依赖：

```powershell
pip install -r requirements.txt
```

配置模型密钥并启动：

```powershell
$env:DEEPSEEK_API_KEY="your-api-key"
python agent/main.py
```

输入售后问题开始对话，输入 `q` 退出。

## 项目结构

```text
agent/
├── context/       # 系统提示与初始消息组装
├── hooks/         # Loop 和工具调用观察
├── knowledge/     # 事实数据与 Skills
├── loop/          # 父 Agent 核心循环
├── model/         # 模型配置
├── tool/          # 工具声明、handler 与 Subagent
├── main.py        # CLI 和运行环境组装
└── middleware.py  # 工具权限边界

evals/             # 本地评估用例与报告入口
```
