# Stage 08：PostgreSQL Checkpoint 与 Redis 缓存

## 本阶段目标

将 Stage 07 的进程内 `InMemorySaver` 换成 PostgreSQL 持久化 Checkpointer，并为只读订单查询加入 Redis 缓存。

本阶段完成后，系统具备两种完全不同的数据能力：

```text
LangGraph 对话状态、审批暂停点
  ↓
PostgreSQL（持久、可跨服务重启恢复）

订单状态的短期查询副本
  ↓
Redis（高速、可过期、可主动失效）
```

不要把两者混为一谈。PostgreSQL Checkpoint 是 LangGraph 状态的可信持久化位置；Redis 是可丢失的缓存副本，不是订单或审批的唯一事实来源。

本阶段不做数据库迁移框架、真实订单表、Redis 分布式锁、缓存指标、限流或生产集群部署；它们属于后续可靠性和交付阶段。

## 最终架构

```text
FastAPI lifespan 启动
  ├─ Redis.from_url() → PING
  ├─ 加载 MCP order_get_status Tool
  ├─ 用缓存包装 Tool 替换原始订单 Tool
  ├─ AsyncPostgresSaver.from_conn_string()
  ├─ await checkpointer.setup()
  └─ 创建 Multi-Agent Graph

POST /chat
  ↓ await graph.ainvoke(..., thread_id)
PostgreSQL 保存每个 checkpoint
  ↓
Supervisor（只看最新 HumanMessage）
  ↓
order_agent → cached order_get_status
  ├─ Redis 命中：返回缓存 JSON
  └─ Redis 未命中：调用 MCP → 提取业务 JSON → SETEX 60 秒

DELETE /admin/threads/{thread_id}
  ↓ await adelete_thread()
PostgreSQL 删除该会话全部 checkpoint

DELETE /admin/cache/orders/{order_id}
  ↓ await OrderStatusCache.invalidate()
Redis 删除 order-status:v1:{order_id}
```

## 新增与修改的文件

```text
compose.yml                         # PostgreSQL 16 + Redis 7，本地 Docker 基础设施
app/settings.py                     # 连接字符串、必填环境变量、缓存 TTL 校验
app/runtime.py                      # Windows Psycopg 异步事件循环兼容层
app/cache.py                        # 可注入的 OrderStatusCache
app/cached_tools.py                 # MCP Tool 的缓存包装器
app/main.py                         # lifespan 资源生命周期、异步管理接口
app/supervisor.py                   # Supervisor 只使用最新用户消息
scripts/check_infrastructure.py     # PostgreSQL、Redis 连通性检查
scripts/check_postgres_checkpoint.py # 跨数据库连接的 checkpoint 持久化验证
tests/test_settings.py              # URL 编码和 TTL 环境配置测试
tests/test_order_status_cache.py    # 缓存命中、写入、TTL、失效测试
tests/test_cached_order_tool.py     # 缓存包装 Tool 的未命中/命中/契约测试
tests/test_supervisor_node.py       # 历史 Tool 消息隔离回归测试
```

## 第一步：启动基础设施

`compose.yml` 使用两个本地容器：

```text
PostgreSQL 16  → 127.0.0.1:5432
Redis 7        → 127.0.0.1:6379
```

环境变量保存在未提交的 `.env` 中，提交的 `.env.example` 只保留变量名和安全的默认值。需要的变量包括：

```env
POSTGRES_DB=enterprise_support
POSTGRES_USER=enterprise_app
POSTGRES_PASSWORD=
POSTGRES_PORT=5432
POSTGRES_HOST=127.0.0.1
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_DB=0
ORDER_STATUS_CACHE_TTL_SECONDS=60
```

验证命令：

```powershell
docker compose up -d
docker compose ps
python -m scripts.check_infrastructure
```

实际结果：PostgreSQL 成功读取 `enterprise_support / enterprise_app`；Redis 成功完成带 10 秒 TTL 的读写。

## 第二步：连接配置不硬编码

`app/settings.py` 通过 `require_env()` 让缺少配置在启动时立即失败。PostgreSQL 密码和用户名必须经过 `quote(..., safe="")` 编码：密码中若包含 `@`、空格等 URL 保留字符，直接拼接连接串会把连接解析坏。

```python
def postgres_connection_string() -> str:
    user = quote(require_env("POSTGRES_USER"), safe="")
    password = quote(require_env("POSTGRES_PASSWORD"), safe="")
    return f"postgresql://{user}:{password}@{host}:{port}/{database}"
```

缓存 TTL 必须是正整数。不能把非法值静默当作默认值，否则配置错误会变成难以发现的缓存异常。

```python
def order_status_cache_ttl_seconds() -> int:
    raw_value = os.getenv("ORDER_STATUS_CACHE_TTL_SECONDS", "60")
    ttl_seconds = int(raw_value)
    if ttl_seconds <= 0:
        raise RuntimeError("ORDER_STATUS_CACHE_TTL_SECONDS 必须是正整数。")
    return ttl_seconds
```

## 第三步：PostgreSQL Checkpointer

以前的 `InMemorySaver` 只保存当前 Python 进程内的字典。服务重启、多个 Worker 或另一台机器都看不到旧状态。

现在 `lifespan` 持有 `AsyncPostgresSaver`：

```python
async with AsyncPostgresSaver.from_conn_string(
    postgres_connection_string()
) as checkpointer:
    await checkpointer.setup()
    app.state.checkpointer = checkpointer
    app.state.graph = create_multi_agent_graph(
        checkpointer=checkpointer,
        ...,
    )
    yield
```

- `from_conn_string()` 打开 Psycopg 异步连接。
- `setup()` 创建 LangGraph Checkpointer 所需的表；它可以重复调用。
- `yield` 前执行启动；服务关闭时 `async with` 自动关闭连接。
- Graph 继续使用相同的 `thread_id` 配置，因此 Graph 编排代码无需因为持久化改写。

### 为什么管理接口必须改为异步

`AsyncPostgresSaver` 的同步包装方法不能在其所属的事件循环中阻塞等待：那会导致“事件循环等任务、任务又等事件循环”的死锁。故应用使用：

```python
await checkpointer.aget_tuple(config)
await graph.aget_state(config)
await checkpointer.adelete_thread(thread_id)
```

而不是同步的 `get_tuple()`、`get_state()`、`delete_thread()`。

### Windows 兼容性

Windows 默认 `ProactorEventLoop` 与 Psycopg 异步模式不兼容。`app/runtime.py` 在 Windows 上配置 `WindowsSelectorEventLoopPolicy`。独立脚本也在 `asyncio.run()` 前设置该策略。

### 实际持久化验收

`scripts/check_postgres_checkpoint.py`：

1. 用第一个数据库连接写入第一条消息；
2. 关闭该连接；
3. 用第二个全新连接、相同 `thread_id` 写入第二条消息；
4. 读到两条消息并断言顺序正确。

真实 HTTP 验收使用 `postgres-persistence-demo-001`：服务重启后，`GET /admin/threads/{thread_id}` 仍返回 4 条消息（用户、模型 Tool 调用、Tool 结果、最终回答）。随后 `DELETE /admin/threads/{thread_id}` 返回 200，再读返回 404。

## 第四步：Redis Cache-Aside

`OrderStatusCache` 只负责 Key、JSON 序列化、TTL 与失效，不负责创建 Redis 连接：连接由 FastAPI lifespan 注入。因此单元测试可以传入 `FakeRedis`，无需真的启动 Redis。

```python
def make_key(self, order_id: str) -> str:
    return f"order-status:v1:{order_id}"

async def set(self, order_id: str, payload: dict[str, Any]) -> None:
    await self.redis.set(
        self.make_key(order_id),
        json.dumps(payload, ensure_ascii=False),
        ex=self.ttl_seconds,
    )
```

Key 的三段分别是业务域、缓存格式版本、业务 ID。将来修改 JSON 格式时可以使用 `v2`，而不会误读旧值。

### 为什么要包装 MCP Tool

MCP 原始响应含有一次调用临时生成的 `id`，它不是业务事实，不能作为缓存内容。`create_cached_order_status_tool()` 完成以下工作：

```text
调用 order_get_status(1002)
  ↓
cache.get("1002")
  ├─ 命中：返回稳定业务 JSON
  └─ 未命中：await source_tool.ainvoke(...)
                 ↓
               从 MCP text 中 JSON 解析出 order_id / found / status
                 ↓
               cache.set(..., TTL)
                 ↓
               返回稳定业务 JSON
```

包装后的 Tool 保留原始名称、描述和 `args_schema`，因此 LangGraph 和模型仍然只看到 `order_get_status`，不会感知缓存实现。

## 第五步：缓存失效

读取缓存不是最终一致性策略的全部。订单状态发生写入时，应主动失效对应 Key；TTL 只是兜底。

本阶段提供管理员接口：

```text
DELETE /admin/cache/orders/{order_id}
Header: x-admin-token: <ADMIN_API_TOKEN>
```

它调用 `await request.app.state.order_cache.invalidate(order_id)`。生产中通常由订单状态更新事件或写服务自动调用，而不由人工操作。

实际验收：先查询订单 `1002`，Redis 中出现 JSON，TTL 为 46；调用失效接口后 `GET` 返回空，`TTL` 返回 `-2`（Key 不存在）；再次查询成功后重新写入缓存。

## 遇到的问题与修复

### 1. Psycopg Windows 事件循环错误

错误信息：`Psycopg cannot use the 'ProactorEventLoop'`。

原因：Psycopg 异步连接不支持 Windows 默认 Proactor 事件循环。

修复：在脚本和应用运行时使用 Selector 事件循环策略。

### 2. 异步函数测试返回 coroutine

将 `has_pending_interrupt()` 改为异步后，旧测试没有 `await`，断言的对象变成 coroutine。测试替身改为异步 `aget_state()`，并使用 `asyncio.run()` 执行协程。

### 3. Supervisor 结构化输出解析失败

多轮会话中，Supervisor 接收了历史 `order_get_status` Tool 消息。模型在应输出 `SupervisorDecision` 时错误输出了订单 Tool 调用，解析器报：`Unknown tool type: 'order_get_status'`。

修复：Supervisor 只使用最新 `HumanMessage` 作路由输入；新增回归测试验证历史 Tool 消息不会进入结构化路由模型。

## 验证证据

```text
基础设施检查：PostgreSQL 连接成功；Redis 读写成功
PostgreSQL 独立跨连接 checkpoint 验证：通过
PostgreSQL 重启后会话读取：4 条消息，成功
指定 thread 删除：DELETE 200，后续 GET 404
缓存组件单元测试：4 passed
缓存包装 Tool 单元测试：3 passed
最终完整测试：79 passed
真实 Redis：写入 JSON，TTL 46 → 17（第二次命中未重置）
真实缓存失效：TTL -2；再次查询后成功回填
```

## 面试要点

1. **为什么 PostgreSQL 而不是 InMemorySaver？**
   `InMemorySaver` 只能在一个进程内使用；PostgreSQL 使 `thread_id` 状态能跨重启和多实例共享，并能恢复 HITL 暂停点。
2. **为什么 PostgreSQL 而不是 MySQL？**
   不是因为 MySQL 不能异步；两者都能。这里选择 PostgreSQL 是因为 LangGraph 提供官方 Postgres Checkpointer，且后续 JSON、审计、事务与异步 Python 生态契合。
3. **Redis 是主数据库吗？**
   不是。它只存订单查询副本；订单服务和 PostgreSQL Checkpoint 才是可信来源。
4. **缓存一致性如何处理？**
   使用 Cache-Aside：读未命中时回源并写缓存；写订单时主动删除 Key；TTL 兜底。
5. **什么是缓存穿透、击穿、雪崩？**
   穿透是大量不存在 Key 持续回源，可做参数校验或短 TTL 的负缓存；击穿是热点 Key 过期时并发回源，可用锁/单飞；雪崩是大量 Key 同时过期或 Redis 故障，可让 TTL 加随机抖动并做降级限流。
6. **为什么缓存 Key 要带 `v1`？**
   它隔离数据格式版本。缓存 JSON 变化后使用 `v2`，避免新代码读取旧结构。

## 阶段复盘

Stage 08 完成后，系统第一次具备了跨服务重启的 Agent 状态恢复能力，以及可观察、可失效的共享查询缓存。这里最重要的边界是：PostgreSQL 保存 Agent 的过程状态；Redis 加速可重复的只读查询。两者不能互相替代。

下一阶段将加入 Trace ID、结构化日志、超时、重试、结构化输出校验与更清晰的安全边界，使当前架构在失败和异常输入下也能被定位、控制和解释。
