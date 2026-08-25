# Stage 05：Checkpoint、会话记忆与线程隔离

## 本阶段目标

让同一个客服会话的后续请求能读取之前消息，让不同会话之间不串线。实现采用 LangGraph `InMemorySaver` 和请求中的 `thread_id`。

本阶段不做跨重启持久化、登录鉴权、对话压缩或长期记忆向量化；它们分别在 Stage 08 和 Stage 09 后继续完善。

## 核心概念

`thread_id` 不是 Python 操作系统线程，也不是新开一个 FastAPI 服务线程。它是 Checkpointer 的逻辑主键，用于定位一条对话 State 的历史快照链：

```text
thread_id = demo-customer-a
  checkpoint 1 → checkpoint 2 → checkpoint 3

thread_id = demo-customer-b
  checkpoint 1 → checkpoint 2
```

每次 Graph 执行时，Checkpointer 先按 `thread_id` 读取最新 State，再将本次节点更新写成新的 checkpoint。当前 State 中的 `messages` 使用 `add_messages` reducer，因此新的 `HumanMessage` 会追加到历史消息列表，而非覆盖它。

## 实现结构

```text
POST /chat
  {thread_id, message}
       ↓
FastAPI lifespan
  创建一个 InMemorySaver
       ↓
create_graph(mcp_tools, checkpointer)
  编译带 checkpoint 的 Graph
       ↓
/chat graph.ainvoke(..., config={thread_id})
       ↓
读取该线程旧 State → 执行 Agent/Tool → 保存新 State
```

关键文件：

```text
app/agent.py
  create_graph(mcp_tools, checkpointer)
  builder.compile(checkpointer=checkpointer)

app/main.py
  lifespan 中创建 InMemorySaver
  ChatRequest 要求 thread_id
  /chat 将 thread_id 放入 configurable config

tests/test_checkpoint_memory.py
  不依赖 LLM、MCP 或 FastAPI，直接验证 State 累积和隔离
```

## 逐步实现与原因

### 1. Graph 接收抽象 Checkpointer

`create_graph()` 增加参数：

```python
def create_graph(
    mcp_tools: list[BaseTool],
    checkpointer: BaseCheckpointSaver,
):
```

并在编译时传入：

```python
builder.compile(checkpointer=checkpointer)
```

函数依赖 `BaseCheckpointSaver`，而不是直接依赖 `InMemorySaver`。这使 Graph 编排逻辑不需要在 Stage 08 改写：到时只替换调用方提供的 Saver 为 PostgreSQL 实现。

### 2. 生命周期内创建 InMemorySaver

FastAPI 的 `lifespan` 在服务启动时创建一次：

```python
checkpointer = InMemorySaver()
app.state.graph = create_graph(mcp_tools, checkpointer)
```

这样所有请求使用同一个内存 Saver，能看到各自线程已有的 State；如果在每次 `/chat` 请求中 `InMemorySaver()`，记忆会在请求结束时丢失。

`InMemorySaver` 的数据只存在当前 Python 进程：重启 Uvicorn、代码热重载或部署新副本都会清空它。因此它适合学习、调试和测试，而不是生产持久化方案。

### 3. API 显式要求 thread_id

请求从：

```json
{"message": "订单 1002 到哪里了？"}
```

变成：

```json
{
  "thread_id": "demo-customer-a",
  "message": "订单 1002 到哪里了？"
}
```

`thread_id` 通过 LangGraph 的运行配置传入，而不是塞进业务 State：

```python
config={
    "configurable": {
        "thread_id": body.thread_id,
    }
}
```

它告诉 Checkpointer 从哪里读取和写入 State；模型不需要把它当成用户可见的对话内容。

### 4. 使用异步 Graph 调用

项目已在 Stage 04 使用 `graph.ainvoke()`，本阶段继续保留该方式。它既能等待异步 MCP Tool，也能让支持异步方法的 Checkpointer 与 Graph 协作。`InMemorySaver` 提供异步接口；未来替换为 `AsyncPostgresSaver` 时，API 层调用形式不变。

## 实际行为

```text
第一次，thread_id=A：
  HumanMessage("我正在查询订单 1002")
  → 没有旧 State
  → 执行后保存 messages

第二次，thread_id=A：
  HumanMessage("我刚才查询的是哪个订单？")
  → 读取 A 的旧 messages
  → add_messages 追加新消息
  → 模型可看到订单 1002 的上下文

首次，thread_id=B：
  HumanMessage("我刚才查询的是哪个订单？")
  → B 没有 A 的 checkpoint
  → 不应知道 1002
```

已在 `/chat` 手动验证同一 `thread_id` 能引用前一轮订单 `1002`，不同 `thread_id` 无法读取该上下文。

## 自动化验证

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 结果：22 passed
```

`tests/test_checkpoint_memory.py` 构建了一个没有 LLM、MCP 和 FastAPI 的最小 Graph：节点不生成业务回答，只让 Graph 形成 checkpoint。因此测试稳定验证了真正需要验证的部分：

1. `thread-a` 的第二次调用结果同时含有第一条和第二条消息。
2. `thread-b` 的首次结果只有自己的消息。
3. `graph.get_state(thread-a config)` 读取到的仍是 `thread-a` 的私有消息。

这种单元测试与手动 API 测试互补：前者验证确定性的 Checkpointer 机制，后者验证 FastAPI 请求、真实模型和完整 Graph 链路。

`tests/test_session_admin.py` 额外验证管理员令牌的三种边界：未配置服务端令牌返回 503、缺少或错误令牌返回 403、正确令牌允许继续执行端点逻辑。

## 开发期线程管理能力

为便于调试和验收，项目新增受保护的管理端点：

```text
GET    /admin/threads/{thread_id}
DELETE /admin/threads/{thread_id}
```

两者都要求 `X-Admin-Token` 请求头与 `.env` 中的 `ADMIN_API_TOKEN` 一致。`.env.example` 只保留空占位，真实令牌不会进入 Git。

读取端点先用 `checkpointer.get_tuple()` 判断该线程是否存在，再通过 `graph.get_state()` 返回最新 messages 和数量；删除端点调用 `checkpointer.delete_thread(thread_id)`。实际手动验证了：

1. 管理员可读取指定 thread 的按序 messages。
2. 可删除该 thread 的 checkpoint。
3. 删除后再次读取返回 404。
4. 未配置、缺少或错误的管理员令牌不会读取会话内容。

## Checkpoint、向量库与数据库的区别

| 组件 | 解决的问题 | 当前项目用途 |
|---|---|---|
| Checkpointer | 精确、按顺序保存 Graph State | 同一对话的消息上下文 |
| Chroma 向量库 | 按语义找相近非结构化文本 | 退款政策等 RAG 文档 |
| PostgreSQL | 长期保存结构化业务与会话数据 | Stage 08 的生产级 State 持久化 |

不能用向量库替代实时聊天 State：向量检索可能漏掉、重排或近似匹配历史内容，无法保证消息顺序和完整回放。长期记忆可以在以后把较长对话摘要后选择性写入数据库或向量库，但那是不同层级的能力。

## 安全边界与常见错误

### thread_id 隔离不是鉴权

当前客户端直接提交 `thread_id`，所以它实现的是状态分桶而非权限控制。若攻击者能猜到其他人的 thread ID，理论上可能请求同一状态桶。真实系统必须把 thread ID 与已认证用户或服务端会话绑定，使用不可预测 UUID，并在读取状态前做授权检查。

因此，本阶段只开放带 `X-Admin-Token` 的开发/管理员端点，而不开放公开的 `GET /threads/{thread_id}` 或删除接口。这个令牌机制适合本地学习和受控内部调试；生产环境仍应使用登录身份、角色授权、审计日志和用户归属校验，而不能把静态管理员令牌当成完整权限系统。

### 常见错误

| 表现 | 根因 | 修复 |
|---|---|---|
| 每轮都忘记上一句 | 每次请求创建了新的 Saver | 在 lifespan 中创建一次并复用 |
| 请求报缺少配置 | 编译了 Checkpointer 但调用没有 thread_id | `ainvoke` 传入 `configurable.thread_id` |
| 两个用户消息混在一起 | 所有请求用了相同 thread_id | 为每个受信任会话分配独立 ID |
| 重启后记忆消失 | 使用 InMemorySaver | Stage 08 改为数据库 Checkpointer |
| 想用 RAG 修复对话记忆 | 混淆语义检索与精确 State | 对话短期状态使用 Checkpointer |
| 管理端点返回 503 | `.env` 未配置 `ADMIN_API_TOKEN` | 配置随机长令牌后重启服务 |
| 管理端点返回 403 | 缺少或错误 `X-Admin-Token` | 使用正确管理员令牌，生产环境改为身份授权 |

## 阶段验收标准

- [x] Graph 使用 `BaseCheckpointSaver` 编译，后续可替换持久化实现。
- [x] FastAPI lifespan 创建并复用一个 `InMemorySaver`。
- [x] `/chat` 要求并传递 `thread_id`。
- [x] 同一 thread 的后续请求可读取前序上下文。
- [x] 不同 thread 的 State 不会串线。
- [x] 管理员可在令牌保护下查看与删除指定 thread。
- [x] 管理员令牌未配置、缺失或错误时被拒绝。
- [x] 自动化测试全部通过。

## 面试复盘

**问：为什么把 thread_id 放在 config 而不是 State？**

它用于选择 Checkpointer 的读写分区，是运行配置，不是模型应该分析的业务内容。State 保存的是消息、工具结果和业务变量。

**问：Checkpoint 在什么时机保存？**

带 Checkpointer 的 LangGraph 会在 Graph 执行步骤中保存 State 快照；一个 thread 会形成多个 checkpoint，而非只保存最终回答。

**问：InMemorySaver 能上线吗？**

不适合生产：进程重启丢失，多个实例也不共享内存。它适合本地学习和测试；生产需要 PostgreSQL 等共享持久化 Saver。

**问：为什么不用向量数据库记忆聊天？**

向量库用于近似语义检索，不能保证完整、顺序和精确隔离；当前对话状态应由 Checkpointer 直接保存。

## 扩展练习

1. 为 `thread_id` 增加 UUID 格式校验，并讨论它为什么仍不能替代登录鉴权。
2. 让前端首次进入时生成 thread ID 并保存在浏览器 session storage，比较刷新页面和新开标签页的差异。
3. 为管理员端点增加操作审计记录，且只记录 thread ID 与操作类型，不记录聊天正文。
4. 记录每个 thread 的消息数量；当消息过多时，设计“摘要 + 保留最近 N 条”的压缩策略。

## 阶段结论

Stage 05 已完成：Agent 具有基于 Checkpoint 的短期对话记忆与线程隔离。下一阶段将为工单正式创建等写操作加入人工审批，学习 LangGraph `interrupt` 与 `resume` 如何安全地暂停和恢复同一 thread。
