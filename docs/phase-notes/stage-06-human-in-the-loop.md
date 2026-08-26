# Stage 06：Human-in-the-Loop 工单审批

## 本阶段目标

为“正式创建工单”这种写操作加入人工审批（Human-in-the-Loop，简称 HITL）。Agent 可以根据用户意图准备工单草稿，但不能自行提交；只有人工确认后，Graph 才会恢复并调用正式创建 Service。

本阶段实现的是一个本地学习版审批流。它使用 Stage 05 的 `InMemorySaver` 保存暂停状态，尚未实现生产级身份认证、审批人授权、数据库持久化和多实例共享，这些会在后续阶段继续完善。

## 最终行为

```text
用户：为客户 c-100 创建高优先级工单：订单迟迟未送达
  ↓
POST /chat（携带 thread_id）
  ↓
LLM 调用 prepare_create_ticket
  ↓
Tool 只生成 TicketDraft，绝不产生写操作
  ↓
capture_ticket_draft 识别 pending_confirmation 草稿
  ↓
request_ticket_approval 调用 interrupt(...)
  ↓
FastAPI 返回 pending_approval + 草稿
  ↓
人工调用 POST /tickets/approval
  ↓
Command(resume={approved: true/false}) 恢复同一 thread_id
  ├─ true  → create_ticket_from_draft → 正式创建
  └─ false → 取消草稿，不执行创建
```

## 前置知识

1. Stage 02 的 Tool、Pydantic 输入模型、业务错误码和“草稿不等于正式写入”。
2. Stage 05 的 `thread_id`、Checkpointer 与同一会话 State。
3. LangGraph StateGraph 的节点、边和条件路由。
4. HTTP `409 Conflict`：客户端请求与服务端当前资源状态冲突时使用，例如恢复一个并不存在或已处理的审批。

## 关键文件

```text
app/
├─ agent.py                 # 草稿识别、审批 interrupt、Graph 路由
├─ main.py                  # /chat 暂停响应、/tickets/approval 恢复接口
├─ schemas.py               # TicketDraft、CreatedTicket
└─ services/
   └─ tickets.py            # 草稿生成、正式创建、按草稿幂等

tests/
├─ test_ticket_service.py               # 正式创建与幂等性
├─ test_ticket_draft_capture.py         # ToolMessage → pending_ticket
├─ test_ticket_approval_interrupt.py    # interrupt / Command resume
├─ test_ticket_approval_graph.py        # 节点和边连接
├─ test_interrupt_response.py            # Graph interrupt → HTTP 响应转换
└─ test_pending_interrupt.py             # 仅恢复暂停中的 thread
```

## 设计一：草稿和正式工单分离

`TicketDraft` 表示等待确认的意图，状态固定为 `pending_confirmation`；`CreatedTicket` 表示已经写入的工单，状态固定为 `created`。两者分开使程序能够明确回答一个关键问题：当前数据是否已经产生业务副作用。

```python
class TicketDraft(BaseModel):
    ticket_id: str
    customer_id: str
    title: str
    priority: Literal["low", "normal", "high"]
    status: Literal["pending_confirmation"]
```

`prepare_create_ticket()` 仅校验规则并生成草稿；`create_ticket_from_draft()` 才是唯一允许创建正式工单的入口。这样即使模型说“已经为您创建”，真正的写操作也必须经过程序边界。

## 设计二：正式创建必须幂等

`create_ticket_from_draft()` 以 `draft.ticket_id` 为键维护已创建结果：

```text
同一草稿第一次确认 → 创建 T-xxxx
同一草稿再次执行 → 返回第一次的 T-xxxx
```

幂等性不能被“用户通常只点一次”替代。网络重试、前端重复点击、进程在响应前失败或人工误操作，都会带来重复调用的可能。当前用进程内字典演示该概念；生产环境应通过数据库唯一约束和事务完成。

## 设计三：从 ToolMessage 提取业务 State

ToolNode 的执行结果会被写成 `ToolMessage`，其 `content` 是 Tool 返回的 JSON。`capture_ticket_draft()` 的职责不是让模型“理解”草稿，而是由确定性程序完成以下校验：

1. 最后一条消息必须是 `ToolMessage`；
2. Tool 名必须是 `prepare_create_ticket`；
3. JSON 必须能解析为字典；
4. `ok` 必须为 `true`；
5. `data` 必须符合 `TicketDraft`；
6. 草稿状态必须为 `pending_confirmation`。

只有全部满足，函数才返回：

```python
{"pending_ticket": draft.model_dump()}
```

`pending_ticket` 放在 Graph State 中，而不是仅存在模型自然语言回答里。模型输出可变，但 State 是程序可验证、可路由、可 checkpoint 的业务数据。

## 设计四：Graph 的显式审批分支

原来的 Tool 回环是：

```text
agent → tools → agent
```

本阶段替换为：

```text
agent → tools → capture_ticket_draft
                    ├─ 无待确认草稿 → agent
                    └─ 有待确认草稿 → request_ticket_approval → END
```

`route_after_tools()` 只根据 `pending_ticket` 决定下一节点。订单查询、RAG、失败的工单准备均没有草稿，因此仍回到 `agent`；不会因为“任何 Tool 都执行过”就误进审批流程。

特别注意：注册节点不等于连接节点。曾经出现过 `capture_ticket_draft` 已注册但仍保留 `tools → agent` 旧边的情况，此时模型会直接继续回答，审批节点根本不会运行。测试因此同时检查节点和关键边。

## 设计五：interrupt 与 resume

审批节点的核心是：

```python
decision = interrupt(
    {
        "type": "ticket_approval",
        "message": "请确认是否正式创建工单。",
        "draft": draft.model_dump(),
    }
)
```

第一次运行到 `interrupt()` 时：

1. LangGraph 保存当前 State checkpoint；
2. Graph 停止；
3. `interrupt()` 中的字典通过 Graph 结果中的 `__interrupt__` 返回；
4. `interrupt()` 后面的代码不会在第一次运行时执行。

恢复时必须使用同一个 `thread_id`：

```python
await graph.ainvoke(
    Command(resume={"approved": True}),
    config=thread_config(thread_id),
)
```

恢复不是从 `interrupt()` 那一行的下一条 Python 语句开始。该节点会从函数开头重新执行，直到抵达同一个 `interrupt()`；此时 `interrupt()` 返回 `Command(resume=...)` 中的值，之后的代码才继续运行。

因此，任何不可重复的写操作都不能放在 `interrupt()` 之前。当前实现先读取并校验草稿，暂停；恢复后才按 `approved` 决定调用 `create_ticket_from_draft()`。

## API 契约

### 发起创建：POST /chat

请求：

```json
{
  "thread_id": "hitl-demo-003",
  "message": "为客户 c-100 创建高优先级工单：订单迟迟未送达"
}
```

暂停时响应：

```json
{
  "status": "pending_approval",
  "thread_id": "hitl-demo-003",
  "approval": {
    "type": "ticket_approval",
    "message": "请确认是否正式创建工单。",
    "draft": {
      "ticket_id": "T-DRAFT-...",
      "customer_id": "c-100",
      "title": "订单迟迟未送达",
      "priority": "high",
      "status": "pending_confirmation"
    }
  }
}
```

`get_interrupt_payload()` 将 LangGraph 内部 `__interrupt__` 协议转换为稳定的业务响应，避免客户端依赖框架对象结构。

### 审批：POST /tickets/approval

请求：

```json
{
  "thread_id": "hitl-demo-003",
  "approved": true
}
```

确认后的响应：

```json
{
  "status": "completed",
  "thread_id": "hitl-demo-003",
  "approved": true,
  "answer": "工单已正式创建，工单编号为 T-...。"
}
```

拒绝后的响应：

```json
{
  "status": "completed",
  "thread_id": "hitl-demo-reject-001",
  "approved": false,
  "answer": "工单草稿已取消，未执行正式创建。"
}
```

服务端通过 `graph.get_state(thread_config(thread_id))` 检查 State 的任务是否真的包含 interrupt。不存在待处理审批时返回 HTTP 409：

```json
{
  "detail": "该 thread_id 没有待处理的人工审批。"
}
```

## 验证方式与实际结果

自动化测试覆盖：

1. `TicketDraft → CreatedTicket` 的成功创建和同草稿幂等性；
2. 被限制客户不能准备或正式创建工单；
3. 成功 ToolMessage 被识别为 `pending_ticket`，失败 Tool 不触发审批；
4. 路由在有草稿时进入审批节点，否则回到 Agent；
5. 独立 Graph 首次调用产生 interrupt，`Command(resume=...)` 后分别得到确认与拒绝结果；
6. 编译图中存在 `tools → capture_ticket_draft`，旧的 `tools → agent` 边不存在；
7. interrupt payload 的 HTTP 转换和“是否存在待恢复审批”的判断。

已手动验证：

- `/chat` 对工单请求返回 `pending_approval`，不产生正式工单编号；
- `approved: true` 后才返回正式工单编号；
- `approved: false` 返回取消信息，未创建工单；
- 不存在或未暂停的 thread 调用审批接口返回 409；
- 完整测试套件通过。

## 常见错误与调试

| 表现 | 根因 | 检查与修复 |
|---|---|---|
| `/chat` 返回普通回答而非 `pending_approval` | 旧的 `tools → agent` 边仍存在 | 确认 Tool 后先进入 `capture_ticket_draft` |
| 草稿未被识别 | Tool 名、JSON、`ok` 或 `status` 不符合预期 | 单测 `capture_ticket_draft`，检查最后一条 ToolMessage |
| `NameError: request_ticket_approval` | 测试文件未导入函数 | 添加 `from app.agent import request_ticket_approval` |
| 恢复后 `messages[-1]` 报 `IndexError` | 审批节点没有返回 `AIMessage` | 确认确认和拒绝分支都返回 `messages` |
| 409 Conflict | thread 不存在、已完成、被热重载清空，或不是暂停状态 | 重新通过 `/chat` 创建草稿，再审批 |
| 服务重载后找不到旧审批 | `InMemorySaver` 只在当前进程内保存 | Stage 08 换持久化 Checkpointer |
| 重复创建工单 | 写操作在 interrupt 前或 Service 不幂等 | 把写操作放在 resume 后，并以 draft ID 去重 |

## 安全边界

当前 `/tickets/approval` 只验证 thread 是否暂停，尚未验证“发起审批的人是否有权审批该工单”。本地学习环境中这足以说明机制，但不能直接上线。

生产系统至少应做到：

1. 通过登录身份确定审批人，而不是信任客户端传来的身份字段；
2. 将 thread、草稿、客户与用户/角色关联；
3. 在恢复前授权检查审批人是否具备权限；
4. 记录审批人、时间、决定与草稿摘要的审计日志；
5. 用数据库唯一约束代替进程内字典实现幂等；
6. 用共享持久化 Checkpointer 支持重启和多副本部署。

## 阶段验收标准

- [x] 创建工单先生成草稿，未确认前不产生正式写操作。
- [x] `pending_ticket` 作为 Graph State 保存，且只由合法 Tool 结果生成。
- [x] Graph 明确区分普通 Tool 回环与审批分支。
- [x] `interrupt()` 返回可展示的草稿信息。
- [x] 同一 `thread_id` 能通过 `Command(resume=...)` 恢复审批。
- [x] 确认后正式创建，拒绝后取消。
- [x] 正式创建按 draft ID 幂等。
- [x] 不存在待审批 interrupt 的恢复请求返回 409。
- [x] 自动化测试和确认、拒绝、错误路径手动验证均已通过。

## 面试复盘

**问：为什么不能在 Tool 中直接创建工单？**

模型可能误调用、参数可能不完整，且用户还没有确认。Tool 应先产生可审查草稿；正式写入必须经过确定性的审批分支。

**问：为什么 `interrupt()` 前不能做写操作？**

Graph 恢复时节点会从头重放。interrupt 前的副作用可能因此重复发生；应把副作用放在 resume 后，并额外做幂等保护。

**问：为什么还需要幂等性，既然接口只允许一个 pending interrupt？**

流程控制减少重复机会，但不能处理网络重试、服务异常、并发或未来接口演进。幂等性是写操作本身的最终保护层。

**问：`thread_id` 是审批权限吗？**

不是。它只是 Checkpointer 定位 State 的键。生产中还需要认证用户、资源归属和角色授权。

**问：为什么无效恢复返回 409 而不是 404？**

接口处理的是“恢复审批”这一状态转换。即使 thread 曾经存在，只要当前没有暂停中的审批，操作都与当前 State 冲突，因此 409 更贴切。

## 扩展练习

1. 在草稿中加入过期时间，过期后拒绝恢复。
2. 支持 `approved: true` 之外的审批备注，并将备注写进 CreatedTicket。
3. 设计“主管审批”和“客服审批”两级流程，讨论 State 中应如何记录当前审批阶段。
4. 为审批接口设计用户身份与客户归属检查，列出需要的数据库表和索引。
5. 模拟服务重启，观察 InMemorySaver 丢失暂停状态；设计 Stage 08 的恢复策略。

## 阶段结论

Stage 06 已完成：项目具备安全的“草稿 → 人工确认 → 正式写入”闭环。Agent 可以编排和准备操作，但不能绕过审批边界。下一阶段将把单一 Agent 按订单、知识库和工单职责拆分为 Supervisor 与领域 Agent。
