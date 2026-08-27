# Stage 09：可靠性、可观测性与安全边界

## 本阶段目标

Stage 08 让服务拥有了持久化状态和缓存，但“能完成请求”不等于“发生问题时能定位、能停止、能安全失败”。本阶段为现有 FastAPI + LangGraph 服务增加五类工程能力：

```text
Trace ID             请求的全链路关联键
JSON 日志             机器可检索的运行记录
超时                  防止外部依赖无限等待
安全重试              只恢复幂等读取操作
结构化契约与输入边界  稳定、安全地表达输入、输出和错误
```

本阶段不接入 OpenTelemetry、LangSmith Trace、Prometheus、分布式限流、JWT/OAuth、WAF 或生产密钥管理。这些是后续部署和身份系统的职责。

## 最终请求路径

```text
HTTP 请求
  ↓
TraceIdMiddleware
  ├─ 校验 X-Trace-ID，非法则生成 UUID
  ├─ 写入 request.state.trace_id
  ├─ 返回头写入 X-Trace-ID
  └─ 记录 JSON 请求日志（方法、路径、状态、耗时）
  ↓
FastAPI 输入模型 / Path 参数校验
  ├─ 非法输入 → 422 + ErrorResponse
  ↓
/chat 或 /tickets/approval
  ├─ asyncio.wait_for 的 Agent 总超时
  │    └─ 超时 → 504 + ErrorResponse + Trace ID
  ├─ order_get_status（只读）
  │    └─ Redis miss → MCP 调用可指数退避重试
  └─ 成功 → Pydantic response_model
  ↓
统一异常处理器
  ├─ 403 / 404 / 409 / 503 / 504 → 稳定 error.code
  ├─ 422 → 不回显原始校验细节
  └─ 未处理异常 → 500 + Trace ID，细节仅留在日志
```

## 文件职责

```text
app/observability.py      # Trace ID、JSON Formatter、请求完成/失败日志
app/reliability.py        # 总超时、重试和明确的领域异常
app/error_handlers.py     # HTTP、校验、未知异常的统一错误响应
app/settings.py           # LLM 与 Agent 超时环境变量校验
app/llm.py                # 把 LLM_TIMEOUT_SECONDS 传给 ChatOpenAI
app/cached_tools.py       # 只读 MCP order_get_status 的重试接入
app/schemas.py            # 成功响应的 Pydantic 契约
app/main.py               # 中间件、异常处理器、response_model、输入边界
tests/test_observability.py       # Trace ID 与日志记录
tests/test_reliability.py         # 超时和退避重试规则
tests/test_chat_timeout.py        # Graph 超时转换为 504
tests/test_error_handlers.py      # 统一错误契约
tests/test_api_response_models.py # 成功响应契约
tests/test_api_input_models.py    # thread_id 输入边界
```

## 一、Trace ID 与结构化日志

### Trace ID 的规则

请求头 `X-Trace-ID` 合法时会被透传；否则服务生成 32 位 UUID 十六进制字符串。合法客户端值必须满足：

```text
首字符：字母或数字
后续最多 63 个字符：字母、数字、-、_
总长度：1 到 64
```

这样做不是认证。它只是帮助调用方把多个服务的同一次请求关联起来，同时避免任意超长或异常字符进入响应头和日志。

```python
TRACE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
)

trace_id = resolve_trace_id(
    request.headers.get("X-Trace-ID")
)
request.state.trace_id = trace_id
```

### 日志内容

`JsonLogFormatter` 将每条日志格式化为单行 JSON。成功请求至少含有：

```json
{
  "event": "http_request_completed",
  "trace_id": "manual-trace-001",
  "method": "GET",
  "path": "/health",
  "status_code": 200,
  "duration_ms": 1.24
}
```

日志不记录请求正文、`ADMIN_API_TOKEN`、模型 API Key 或数据库密码。这样既能定位请求，又不把敏感信息写入终端或日志平台。

## 二、两层超时

### LLM 单次请求超时

`.env` 中的：

```env
LLM_TIMEOUT_SECONDS=30
```

会传给 `ChatOpenAI(timeout=...)`。它限制一次模型 HTTP 调用，不代表整个 Agent 工作流的时间上限。

### Agent 总时间预算

`.env` 中的：

```env
AGENT_TIMEOUT_SECONDS=45
```

通过 `run_with_timeout()` 包裹 `/chat` 和 `/tickets/approval` 的 `graph.ainvoke()`：

```python
await asyncio.wait_for(operation, timeout=timeout_seconds)
```

底层 `TimeoutError` 被转换为 `OperationTimeoutError`。路由捕获后返回受控的 504：

```json
{
  "error": {
    "code": "AGENT_TIMEOUT",
    "message": "Agent 请求超时，请稍后重试。",
    "trace_id": "..."
  }
}
```

### 关键取舍：超时不等于未执行

对只读订单查询，超时后可以在有限次数内重试。对工单审批恢复，超时发生时写入可能已经到达下游，因此系统**不会自动重试审批**，只提示“稍后确认状态”。这是避免重复创建或重复变更业务数据的安全边界。

## 三、只读 MCP 重试

`retry_read_operation()` 接收一个“每次都能创建新协程”的函数，而不是已创建的 coroutine。因为 coroutine 不能被重复 await。

```python
await retry_read_operation(
    lambda: source_tool.ainvoke({"order_id": order_id}),
    operation_name="mcp_order_get_status",
)
```

规则：

| 情况 | 行为 |
|---|---|
| `TimeoutError`、`OSError` / `ConnectionError` | 最多 3 次，0.1s、0.2s 指数退避 |
| `ValueError`、JSON 结构错误、参数错误 | 立即失败，不重试 |
| 三次都无法连接 | 抛出 `RetryExhaustedError` |
| 工单准备、审批恢复 | 不接入自动重试 |

当前重试只接在 `cached_tools.py` 的 `order_get_status` MCP 回源路径。Redis 命中不会调用 MCP，也不会进入重试逻辑。

## 四、统一错误契约

`app/error_handlers.py` 将不同来源的错误收敛为：

```text
403 → FORBIDDEN
404 → NOT_FOUND
409 → CONFLICT
422 → VALIDATION_ERROR
503 → SERVICE_UNAVAILABLE
504 → AGENT_TIMEOUT
其他未处理异常 → INTERNAL_ERROR
```

校验失败不再向调用方回显 Pydantic 的完整内部细节，只返回“请求参数不合法。”；未处理异常不回显 Python 堆栈。完整错误类型和堆栈仅写入 JSON 日志，并以 Trace ID 关联。

## 五、成功响应契约

原本 `/chat` 与审批接口返回未约束的 `dict`。现在 FastAPI `response_model` 使用 Pydantic 约束三类成功结果：

```text
ChatCompletedResponse
  status = completed
  answer

PendingApprovalResponse
  status = pending_approval
  thread_id
  approval.type = ticket_approval
  approval.draft = TicketDraft

TicketApprovalCompletedResponse
  status = completed
  thread_id
  approved
  answer
```

这会让 Swagger 明确展示接口返回结构，也能在服务端意外返回错误字段时尽早失败，而不是让不一致数据悄悄流向调用方。

## 六、输入边界

`thread_id` 同时用于 PostgreSQL Checkpoint、管理员路径和状态隔离；`order_id` 用于 Redis Key。它们在 HTTP 边界统一限制为：

```text
^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$
```

因此空值、空格、`../unsafe`、斜杠和超过 100 个字符的值会得到 `422 VALIDATION_ERROR`。这不是 SQL 注入防护的替代品（数据库仍必须使用参数化查询），而是资源控制、日志可读性与协议一致性的第一层保护。

管理员接口还保留了 `hmac.compare_digest()` 对 `ADMIN_API_TOKEN` 的常量时间比较；Token 不会进入日志。

## 验证证据

```text
Trace ID / JSON 日志测试：通过
LLM timeout 设置测试：通过
Agent 超时与 504 测试：通过
只读重试测试：连接失败重试、ValueError 不重试、耗尽失败均通过
缓存 MCP Tool 重试集成测试：通过
统一错误响应测试：404、422 与 Trace ID 通过
成功响应模型测试：通过
thread_id 输入边界测试：通过
最终完整测试：120 passed in 11.74s
```

## 常见错误与调试方法

| 现象 | 原因 | 检查方式 |
|---|---|---|
| 请求一直等待 | 没有总超时，或时间预算设置过大 | 检查 `AGENT_TIMEOUT_SECONDS` 与 `chat_timeout` 日志 |
| 写操作重复执行 | 对审批/创建操作加了自动重试 | 只允许幂等读取使用 `retry_read_operation()` |
| 504 后以为操作一定失败 | 下游可能已收到请求 | 用 `thread_id` 查询状态或检查业务审计记录 |
| 客户端拿到 Python 堆栈 | 未处理异常直接外泄 | 检查 `unhandled_exception_handler` 与 `INTERNAL_ERROR` 响应 |
| 不同请求无法关联日志 | 调用方未记录响应头的 `X-Trace-ID` | 将响应 Trace ID 一并记录在客户端日志 |

## 面试要点

1. **超时和重试有什么区别？** 超时限定最长等待时间；重试是在可恢复的临时失败后再次尝试。它们通常一起出现，但不能把所有超时都自动重试。
2. **为什么只重试订单查询？** 它是幂等读操作；审批恢复可能已经产生写入，自动重试会带来重复副作用。
3. **为什么有 LLM 超时后还要 Graph 总超时？** 前者保护一次模型 HTTP 调用；后者保护包含多次模型、MCP、数据库和工具调用的整个业务路径。
4. **Trace ID 和 thread_id 的区别？** Trace ID 标识一次 HTTP 请求，用于日志定位；thread_id 标识一段 Agent 会话，用于 Checkpoint、记忆和审批恢复。
5. **为什么不把原始校验错误直接返回？** 框架内部格式不稳定，也可能回显输入和内部字段；对外应提供稳定且最小化的错误契约。
6. **JSON 日志为什么比拼接字符串更好？** 日志系统可按 `trace_id`、`status_code`、`duration_ms` 精确过滤、聚合和告警。

## 阶段复盘

Stage 09 将“正常路径能跑”的 Agent 服务改造成“异常路径可解释、可限制”的服务。最重要的工程判断不是加多少中间件，而是明确副作用边界：读取可有限重试，写入不能盲目重试；超时要有用户可理解的响应，同时保留 Trace ID 供内部定位。

下一阶段将进行 Docker 化交付、分层测试和部署准备，确保本地学习项目能以一致方式被他人启动和验证。
