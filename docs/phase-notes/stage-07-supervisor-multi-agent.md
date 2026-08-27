# Stage 07：Supervisor 与领域 Multi-Agent

## 本阶段目标

将 Stage 06 的单 Agent 客服图拆分为一个 Supervisor 和三个领域 Agent：订单、知识库、工单。Supervisor 只做路由；领域 Agent 只拥有本领域最小必要 Tool；工单写操作继续复用 Stage 06 的人工审批。

目标不是为了增加“Agent 数量”，而是让职责、权限和流程边界可见、可测试：

```text
谁决定请求去向？          Supervisor
谁能查询订单？            order_agent
谁能读取政策文档？        knowledge_agent
谁能准备工单草稿？        ticket_agent
谁能正式创建工单？        仅 HITL resume 后的确定性 Service
```

本阶段没有实现并行多 Agent 协作、跨 Agent 任务分解、跨模型路由或长期可观测性；这些属于后续工程化能力。

## 最终架构

```text
POST /chat
  ↓
LangGraph MultiAgentState + InMemorySaver
  ↓
Supervisor（无业务 Tool，只输出结构化 next_agent）
  ├─ order_agent
  │    ↓
  │  order_tools（仅 MCP order_get_status）
  │    ↓
  │  order_agent → END
  │
  ├─ knowledge_agent
  │    ↓
  │  knowledge_tools（仅 search_knowledge）
  │    ↓
  │  knowledge_agent → END
  │
  ├─ ticket_agent
  │    ↓
  │  ticket_tools（仅 prepare_create_ticket）
  │    ↓
  │  capture_ticket_draft
  │    ├─ 普通 Tool 结果 → ticket_agent
  │    └─ 待确认草稿 → request_ticket_approval → interrupt
  │
  └─ unsupported → 固定范围外拒答 → END

POST /tickets/approval
  ↓
Command(resume={"approved": true/false})
  ↓
同一 thread_id 的 request_ticket_approval
  ↓
确认后正式创建 / 拒绝后取消
```

## 文件职责

```text
app/
├─ llm.py              # 创建模型；支持显式开关 DeepSeek thinking 模式
├─ schemas.py           # SupervisorRoute、SupervisorDecision
├─ supervisor.py        # Supervisor Prompt、结构化输出、路由函数和实验图
├─ domain_agents.py     # 领域 Prompt、Tool 白名单、通用 Agent Tool Loop
├─ multi_agent.py       # 实际运行的主 Multi-Agent Graph
├─ agent.py             # 保留 Stage 06 的草稿捕获与审批节点，供主图复用
└─ main.py              # lifespan 中创建并注入多 Agent Graph

scripts/
├─ preview_supervisor_routing.py  # 真实模型检查 Supervisor 路由
└─ preview_multi_agent.py         # 不启动 HTTP 的完整真实链路预览

tests/
├─ test_supervisor_*.py           # 路由契约、节点和实验图
├─ test_domain_agent_*.py         # Tool 权限边界与领域 Tool Loop
├─ test_multi_agent_graph.py      # 主图订单、知识库、工单暂停、范围外分支
└─ test_multi_agent_app.py        # FastAPI 启动后是否装配 Multi-Agent Graph
```

## 核心概念一：路由契约，而不是自由文本

Supervisor 的输出使用 Pydantic 模型：

```python
SupervisorRoute = Literal[
    "order_agent",
    "knowledge_agent",
    "ticket_agent",
    "unsupported",
]


class SupervisorDecision(BaseModel):
    next_agent: SupervisorRoute
```

模型不能返回“订单专家”或“可能应该查退款政策”这类自然语言；它只能选择已有节点名。`route_after_supervisor()` 再通过 `SupervisorDecision.model_validate()` 校验 State，随后将值交给 LangGraph 的条件边。

```text
模型输出 → SupervisorDecision → next_agent → conditional edge → 领域节点
```

这使模型的不确定性停留在受约束的枚举值中，而不是让模型直接操控 Graph 名称或业务 Tool。

## 核心概念二：Supervisor 不处理业务

Supervisor Prompt 明确禁止回答用户、调用 Tool、创建或修改业务数据。它的单一输出是 `next_agent`。

这和单 Agent 的区别是：

| 单 Agent | Multi-Agent Supervisor |
|---|---|
| 一个模型同时理解、路由、调用所有 Tool、回答 | 一个模型只决定职责归属，领域节点独立执行 |
| 每次调用都暴露完整 Tool 列表 | 每个领域节点只看见自己被授权的 Tool |
| Prompt 越来越大，边界易混淆 | Prompt 和权限随领域拆分 |

这不是“多个模型互相聊天”。当前四个模型实例使用同一个底层模型配置，但扮演不同受限角色；拆分的价值来自职责和 Tool 权限，不来自模型品牌不同。

## 核心概念三：最小权限 Tool 集

`build_domain_toolsets()` 产生以下白名单：

```text
order_agent     → [order_get_status]
knowledge_agent → [search_knowledge]
ticket_agent    → [prepare_create_ticket]
```

即使订单 Agent 的 Prompt 被错误诱导去创建工单，它的 `bind_tools()` 中也不存在 `prepare_create_ticket`。这比“Prompt 要求它不要创建工单”更可靠：Prompt 是软约束，Tool 可见性是硬约束。

订单 Tool 来自 MCP 动态发现结果，因此启动时找不到 `order_get_status` 会抛出错误并拒绝构图。沉默地启动一个缺订单能力的系统会让错误在用户请求时才暴露。

## 核心概念四：领域 Agent 有自己的 Tool Loop

通用 `create_domain_agent_graph()` 说明领域 Agent 的最小闭环：

```text
agent → tools_condition
  ├─ 有 tool_calls → ToolNode → agent
  └─ 无 tool_calls → END
```

主 Multi-Agent 图将这个模式按领域展开，形成 `order_agent → order_tools → order_agent` 与 `knowledge_agent → knowledge_tools → knowledge_agent` 两个独立循环。它们不共享 ToolNode。

Ticket 路径不同：其 Tool 返回草稿后先进入 `capture_ticket_draft`，成功草稿会改走 HITL，而不是立刻回到 ticket_agent 或执行正式创建。

## DeepSeek Structured Output 兼容性

Supervisor 必须输出稳定枚举，因此使用：

```python
model.with_structured_output(
    SupervisorDecision,
    method="function_calling",
)
```

实际调试发现两个协议兼容问题：

1. 默认结构化输出使用 `response_format` JSON Schema 时，当前 DeepSeek 端点返回 `This response_format type is unavailable now`。
2. 改为 `function_calling` 后，DeepSeek V4 Flash 默认 Thinking 模式会拒绝结构化输出内部使用的强制 `tool_choice`，报错 `Thinking mode does not support this tool_choice`。

解决办法是只为 Supervisor 创建非 Thinking 模型：

```python
create_chat_model(thinking="disabled")
```

`app.llm.create_chat_model()` 通过 OpenAI 兼容参数传入：

```python
extra_body={"thinking": {"type": "disabled"}}
```

订单、知识库和工单 Agent 保持默认 thinking 模式。路由是一个低复杂度、需要快速稳定分类的任务，因此关闭 Supervisor 的 thinking 是明确的角色级配置，不是全局降级。DeepSeek 文档说明 V4 Flash 默认启用 Thinking，并可通过 `extra_body.thinking.type` 切换；Thinking 模式对 `tool_choice` 有兼容限制。([Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/), [Chat Completions 参数](https://api-docs.deepseek.com/api/create-chat-completion/))

## RAG 回答边界的真实调试

真实多 Agent 预览中，用户询问“退款审核通过后多久到账？”时，第一次知识库 Agent 正确给出 `3 到 5 个工作日`，但额外补充“支付渠道可能不同”。这不是文档证据，属于常识性幻觉。

第一次收紧 Prompt 后，模型又罗列了同文档中数字商品和定制商品规则。它们确实存在于检索证据中，却与当前问题无关；这不是事实幻觉，而是相关性失败。

最终 Knowledge Prompt 形成三层约束：

```text
事实边界：只能说 Tool 证据直接支持的结论
相关性边界：只说当前问题所需的最少规则
输出形状：单一事实问题只允许“来源 + 直接答案”的短段落，之后结束
```

最终真实预览的合格回答为：

```text
根据 refund-policy.md，退款申请审核通过后，款项将在 3 到 5 个工作日内原路退回。
```

Prompt 不是数学证明，仍不能替代检索质量、测试集和后续 Guardrail；但把错误案例转为 Prompt 回归测试，能防止以后无意移除这些关键约束。

## 依赖注入与测试策略

`create_multi_agent_graph()` 接受四个显式模型实例：

```text
supervisor_model
order_model
knowledge_model
ticket_model
```

生产 lifespan 注入四个真实 `ChatOpenAI` 实例；测试则注入 Fake Supervisor 和 Fake Tool Calling Model。这样单元测试可验证：

1. Supervisor 选择 `order_agent` 时，只有订单模型被调用；
2. 订单模型完成 `Agent → ToolNode → Agent`；
3. 知识库模型只调用 `search_knowledge`；
4. Ticket Agent 的草稿 Tool 结果产生 interrupt，尚未正式创建；
5. `unsupported` 不调用任何领域模型；
6. 模型实例和领域 Tool 集不会在测试中请求真实 API、加载 BGE 或连接 Chroma。

测试入口的 `domain_toolsets` 参数是可选依赖注入：生产省略它并调用真实 `build_domain_toolsets(mcp_tools)`；测试提供内存 Fake Tool，以便只验证编排。

## 实际验证

### 自动化验证

本阶段覆盖的自动化验证包括：

- `SupervisorDecision` 只接受四个已知路由值；
- 未知路由在条件边前被 Pydantic 拒绝；
- Supervisor 节点能将结构化决策写入 State；
- 最小 Supervisor Graph 四条分支均到达预期节点；
- 订单 Agent 的 Tool 集不含工单 Tool；
- 订单领域 Agent 在隔离图中完成一次 Tool Loop；
- Multi-Agent 主图的订单、知识库、工单暂停和范围外分支均通过 Fake Model 集成测试；
- FastAPI lifespan 构建出的图包含 `supervisor`、三个领域节点、审批节点和 `unsupported`。

### 真实模型预览

`python -m scripts.preview_multi_agent` 在不启动 FastAPI 的情况下完成：

```text
订单 1002 到哪里了？
  → order_agent → MCP order_get_status → 正确订单状态

退款审核通过后多久到账？
  → knowledge_agent → 本地 RAG → 仅回答 3 到 5 个工作日和来源

为客户 c-100 创建工单
  → ticket_agent → 草稿 → pending ticket_approval interrupt

北京今天天气怎么样？
  → unsupported → 不调用业务 Tool 的范围外拒答
```

PowerShell 终端一度将中文打印为乱码；这是本地终端编码显示，不是 API、模型或 Graph 返回内容的问题。通过 API/实际内容可确认中文响应正确。

### HTTP 最终验收

在 `/docs` 中使用不同 thread_id 逐项验证：

1. 订单请求返回 `completed` 和 MCP 查询结果；
2. 知识库请求只返回当前问题相关的、带 `refund-policy.md` 来源的事实；
3. 工单请求先返回 `pending_approval`，再由 `/tickets/approval` 使用相同 thread_id 恢复并正式创建；
4. 天气请求由 `unsupported` 直接拒绝。

以上路径均已通过。

## 常见错误与调试方法

| 现象 | 原因 | 修复 |
|---|---|---|
| `response_format type is unavailable` | DeepSeek 不支持当前 JSON Schema response_format 路径 | 使用 `method="function_calling"` |
| `Thinking mode does not support this tool_choice` | Supervisor 在 Thinking 模式下被结构化输出强制 Tool Choice | 仅 Supervisor 用 `thinking="disabled"` |
| Supervisor 输出不存在的节点 | 自由文本或 State 被污染 | `SupervisorDecision` + `model_validate()` |
| 注册了领域节点但仍进入旧单 Agent | FastAPI 仍导入旧 `create_graph` | lifespan 改为 `create_multi_agent_graph` |
| 知识库补充支付渠道常识 | 模型超出证据回答 | 强化事实边界，加入真实回归案例 |
| 知识库罗列同文档无关规则 | 检索证据多于用户问题所需 | 强化相关性边界和单段回答形状 |
| 工单直接创建 | Ticket 路径绕过审批节点 | `ticket_tools → capture_ticket_draft → interrupt` |
| 单元测试加载 BGE 或真实向量库 | 测试直接使用生产 Tool | 通过 `domain_toolsets` 注入 Fake Tool |

## 阶段验收标准

- [x] Supervisor 只选择合法领域节点，不处理业务或持有业务 Tool。
- [x] `order_agent`、`knowledge_agent`、`ticket_agent` 拥有独立 Prompt 和最小 Tool 集。
- [x] 各领域 Tool Loop 在主图中独立存在。
- [x] Ticket 路径保留 Stage 06 的 interrupt/resume 与幂等正式创建。
- [x] DeepSeek V4 Flash 的结构化输出兼容问题被定位并以角色级 Thinking 配置解决。
- [x] 知识库回答经真实模型检查，满足证据和相关性边界。
- [x] Multi-Agent Graph 通过 Fake Model 集成测试。
- [x] FastAPI 已切换到 Multi-Agent Graph，并完成四条真实 HTTP 验收路径。

## 面试复盘

**问：这是不是“多个模型互相对话”？**

不一定。当前实例可以使用相同底层模型；Multi-Agent 的关键是职责拆分、可见的路由和最小权限 Tool 集，而不是模型必须不同。

**问：为什么 Supervisor 不直接调用订单 Tool？**

它负责协调而不是执行。若 Supervisor 也有所有 Tool，权限边界会重新坍塌成单 Agent；领域 Agent 才负责在受限能力中执行任务。

**问：为什么还需要 Prompt，既然 Tool 已做隔离？**

Tool 隔离防止错误调用，Prompt 定义回答边界、语气和何时调用 Tool。两者分别是硬约束和软约束，缺一不可。

**问：为什么为每个角色注入独立模型实例？**

依赖显式、测试可替换。生产中也可按角色选择不同成本、延迟或能力配置；当前角色使用同一模型只是一个实现选择。

**问：RAG 回答为什么会说出同文档但无关的信息？**

检索返回的是候选证据集合，模型可能倾向总结更多内容。Grounding 还需要相关性约束和输出格式，不能只要求“基于文档”。

## 扩展练习

1. 将 `next_agent` 替换为包含置信度和澄清标志的结构化决策，讨论何时需要追问而不是强制路由。
2. 为多个意图设计策略：优先处理、串行处理，或让 Supervisor 生成任务计划；比较复杂度和可解释性。
3. 为每个领域 Agent 配置不同模型、超时和最大 Tool 调用次数。
4. 为 Supervisor 路由建立真实问题测试集，统计混淆矩阵，例如把退款问题误路由到订单 Agent 的比例。
5. 把 Knowledge Agent 的事实/相关性规则从 Prompt 延伸为程序化引用校验或回答后 Guardrail。

## 阶段结论

Stage 07 已完成：FastAPI 的真实服务从单 Agent 切换为 Supervisor + 订单、知识库、工单领域 Agent。系统的能力边界不再只依赖一个大 Prompt，而由结构化路由、独立节点、最小 Tool 权限和已保留的 HITL 共同约束。下一阶段将用 PostgreSQL、Redis 和持久化 Checkpointer 替换当前进程内状态。
