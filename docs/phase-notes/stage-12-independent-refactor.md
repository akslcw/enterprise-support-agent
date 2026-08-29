# Stage 12：独立重构为可写简历版本

## 本阶段目标

在不改变已经验证的多 Agent、MCP、RAG、HITL 与持久化能力的前提下，重构应用的工程边界。目标不是增加新功能，而是让项目能够清楚说明 HTTP 层、应用服务层和 LangGraph 编排层各自负责什么，并让质量检查在干净的 GitHub 环境中自动运行。

本阶段在分支 `refactor/stage-12` 完成，完成后再合并到 `main`。

## 最终结构

```text
HTTP 请求
  ↓
app/api/contracts.py              请求、响应与格式校验
  ↓
app/api/routers/                  HTTP 状态码、依赖与错误映射
  ↓
app/application/                  一次用例的应用编排
  ↓
LangGraph / Checkpointer / Redis / MCP / RAG
```

`app/main.py` 只负责应用装配：启动与关闭资源、注册中间件和异常处理器、挂载 Router。它不再直接承载聊天、审批或线程管理的业务流程。

## 一、Router / Service / Graph 分层

### HTTP Router

新增 `app/api/routers/`：

- `health.py`：健康检查；
- `chat.py`：接收聊天请求，将超时映射为 HTTP 504；
- `tickets.py`：恢复人工审批，并将“没有待审批动作”映射为 HTTP 409；
- `admin.py`：在线程管理路由统一校验管理员令牌，并将不存在的线程映射为 HTTP 404。

Router 的职责是 HTTP 边界：接收经过 Pydantic 校验的输入、取得 FastAPI 依赖、选择 HTTP 状态码、返回 JSON。它不应理解 LangGraph State 的细节，也不应直接拼装 Checkpointer 查询。

### Application Service

新增 `app/application/`：

- `ChatService`：创建 `HumanMessage`、带超时调用 Graph、将原始 Graph 返回值转换为完成或待审批响应；
- `TicketApprovalService`：读取线程状态、确认是否存在 interrupt、使用 `Command(resume=...)` 恢复流程；
- `ThreadAdminService`：读取、删除 Checkpoint，并在删除后失效 Redis 订单缓存。

应用服务表达的是“一个用例如何完成”。例如 `/chat` 的完整调用顺序是：

```text
ChatRequest
  → chat Router
  → ChatService 创建消息与 thread_id config
  → multi-agent graph（Supervisor → domain agent → Tool）
  → ChatService 将 Graph State 转成响应契约
  → Router 返回 HTTP JSON
```

这样测试 `ChatService` 时不需要启动 HTTP Server；测试 Router 时也只需验证输入、依赖和错误映射。

### Contracts

`app/api/contracts.py` 收拢 `ChatRequest`、`ApprovalRequest` 和标识符正则校验。请求模型不再由 `main.py` 隐式拥有，测试也从真实所有者导入，避免“为了兼容测试而让入口文件继续膨胀”。

## 二、兼容性与验证

重构不等于改接口。原有 URL、请求字段、响应结构与错误状态码保持不变；旧测试继续保护订单、知识库、工单审批、Checkpoint 和缓存行为。

本阶段新增或调整的测试覆盖：

1. Router 是否在 OpenAPI 中注册预期路径与 HTTP 方法；
2. `ChatService` 的完成响应、待审批响应和超时路径；
3. `TicketApprovalService` 的同意、拒绝和无待审批动作路径；
4. `ThreadAdminService` 的读取、删除和缓存失效路径；
5. 输入模型与帮助函数从新的真实模块导入。

最终本地结果：

```text
Ruff：All checks passed
Mypy：Success: no issues found in 37 source files
Pytest：132 passed
```

## 三、统一质量配置

新增根目录 `pyproject.toml`：

- 声明项目名称、Python 3.13 要求；
- 统一 pytest 测试目录；
- 用 Ruff 检查常见语法、导入排序、BugBear、现代 Python 写法与异步误用；
- 用 MyPy 检查应用代码，重点限制 `Any` 从第三方库边界泄漏到业务返回值。

新增 `requirements-dev.txt`，在运行依赖基础上补充 `ruff` 和 `mypy`。这区分“服务运行需要什么”与“开发和 CI 额外需要什么”。

RAG 的类型改造说明：Chroma 的集合 API 类型允许文本或图片输入，但 BGE 中文模型只支持文本。`ChineseBGEEmbeddingFunction` 因而声明完整的 Chroma 输入契约，并在运行时明确拒绝图片；`SentenceTransformer` 返回的动态数组在这一第三方边界被受控转换为 Chroma 的 `Embeddings` 类型。`collection.count()` 也显式转换为 `int`。这不是压制类型检查，而是把不确定性限制在适配器边界。

## 四、GitHub Actions CI

新增 `.github/workflows/quality.yml`。当推送到 `main` 或 `refactor/stage-12`，或向 `main` 提交 Pull Request 时，GitHub 会：

```text
启动干净 Ubuntu Runner
  → 启动 PostgreSQL 16 与 Redis 7 服务并等待健康检查
  → 安装 Python 3.13 与开发依赖
  → Ruff
  → MyPy
  → Pytest
```

工作流使用仅用于测试的 PostgreSQL 密码、管理员令牌和模型占位 Key；真实 `.env` 与真实模型密钥绝不提交。测试应 Mock 外部模型调用，因此 CI 不消耗模型额度，也不会把密钥暴露给仓库日志。

## 常见错误与排查

1. **Router 变成第二个 `main.py`**：如果 Router 自己构建 Graph、读写 Redis、遍历 State，应把该流程下沉到 Application Service。
2. **重构后接口悄悄变化**：先保留既有响应契约和状态码，再添加回归测试；不要借重构名义改业务规则。
3. **本机全绿、CI 失败**：CI 是没有本地缓存、没有 `.env`、没有长期运行服务的干净环境。检查工作流 env、服务 health check、依赖文件和是否意外依赖本地 BGE 缓存。
4. **把真实密钥写进 workflow**：应使用 GitHub Secrets；本项目的单元测试不需要真实密钥，因此只用假值。
5. **YAML 因缩进失效**：`.github/workflows/*.yml` 是 YAML 文件，不应包含 Markdown 的 ```yaml 代码围栏；缩进决定结构。

## 面试复盘

1. **为什么 Router 不直接调用 Graph？** Router 负责协议边界，Service 负责用例编排，Graph 负责 Agent 决策。分层降低 HTTP、状态管理和业务逻辑的耦合，并允许分别测试。
2. **为什么保留 LangGraph，而不是把流程都放进 Service？** Service 决定何时调用 Graph；Graph 负责有状态的 Agent 路由、Tool loop、Checkpoint 与 interrupt/resume。两者职责互补。
3. **CI 为什么仍要启动 PostgreSQL 和 Redis？** 单元测试 Mock 模型，但关键集成路径仍需要验证基础设施连接、状态与缓存边界，避免只在开发机成功。
4. **为什么把 RAG 类型问题当作工程质量问题？** 检索模型、向量库和 NumPy 都是外部动态边界。明确输入范围和转换点，能防止不支持的图片或任意 `Any` 进入业务层。
5. **这个阶段最重要的产出是什么？** 不是文件数量，而是可解释、可测试、可自动验证的职责边界；这使项目从“功能能跑”升级为“可维护的个人作品”。

## 阶段验收标准

```text
app/main.py 仅承担装配职责。
聊天、审批、线程管理各有 Router 与 Application Service。
原有 API 契约及多 Agent / MCP / HITL / RAG / Redis 行为保持。
pyproject.toml、Ruff、MyPy 与 requirements-dev.txt 可在新环境安装使用。
本地 Ruff、Mypy、全量 pytest 全部通过。
GitHub Actions 质量工作流已推送，并在远程 Runner 成功执行。
```

## 阶段复盘

本阶段没有为了“看起来更企业化”而推翻项目的业务设计。它保留了当前项目最有辨识度的 Supervisor 多 Agent、MCP Tool、RAG、HITL 和分层存储；重构的是这些能力进入 HTTP 应用的方式。下一阶段可基于这套清晰边界完成项目叙事、简历表达与面试演练。
