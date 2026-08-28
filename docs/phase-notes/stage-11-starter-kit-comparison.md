# Stage 11：开源 Starter Kit 拆解与对照学习

## 本阶段目标

本阶段不复制开源项目，也不对当前服务做架构重写。目标是阅读一个相邻技术栈的公开 Starter Kit，理解它的分层、持久化、认证、测试与交付取舍；再明确哪些能力值得在 Stage 12 独立重构时借鉴，哪些必须保留当前项目的设计，哪些存在缺陷而不能照搬。

对照仓库：[`IgnazioDS/langgraph-fastapi-starter`](https://github.com/IgnazioDS/langgraph-fastapi-starter)，审阅版本 `aa1bed22c0453b1c5accf8fd687d550d7e7db20b`（2026-05-13）。它是 FastAPI + LangGraph + PostgreSQL/pgvector 的公开模板，不是本项目的上游依赖。

## 为什么选择它

该模板与本项目有足够的共同语言：Python、FastAPI、LangGraph、PostgreSQL、Docker、结构化日志、Pydantic 与 pytest。同时它刻意采用单 Agent、单 PostgreSQL/pgvector、API Key 的简化路径，因此能清楚凸显 Enterprise Support Agent 已经实现的 MCP、Redis、Chroma、HITL 和 Supervisor 多 Agent 能力。

学习时不运行其服务、不安装其依赖，也不把它的代码复制进本仓库；只在独立的 `reference-projects/` 目录阅读源代码。

## 一、目录和职责对照

| 当前项目 | Starter Kit | 对照结论 |
|---|---|---|
| `app/main.py` | `app/main.py`、`app/routers/` | 当前项目先以集中入口完成接口；模板将不同 HTTP 资源拆到 router。 |
| `app/agent.py`、`multi_agent.py`、`supervisor.py`、`domain_agents.py` | `app/graph/state.py`、`nodes.py`、`tools.py`、`graph.py` | 当前项目按业务领域与编排能力拆分；模板集中管理一个单 Agent 图。 |
| `app/tools.py`、`cached_tools.py`、`mcp_client.py` | `app/graph/tools.py` | 当前项目增加了 MCP 动态 Tool、Redis 缓存和业务安全边界。 |
| `app/services/` | `app/services/agent_service.py` | 二者都使用应用服务层承接 HTTP 与 Graph/数据库之间的编排。 |
| `app/schemas.py` | `app/models/requests.py`、`responses.py` | 都使用 Pydantic 契约；模板把请求与响应进一步分文件。 |
| PostgreSQL Checkpoint、Redis、Chroma | PostgreSQL + pgvector | 两者的核心差异是“按职责拆服务”与“单库优先简化运维”的取舍。 |

## 二、Graph 设计对照

Starter Kit 的图为：

```text
retrieve（直接检索）
  ↓
agent（LLM）
  ├─ 无 Tool Call → END
  └─ 有 Tool Call → tools（ToolNode）→ agent
```

它的 `AgentState` 保存：消息历史、`session_id`、`tenant_id`、RAG `context`、`run_id`、输入 Token 与输出 Token。提示词不是 State 字段；当有检索结果时，`call_model()` 临时创建 `SystemMessage` 并插入消息列表。

当前项目则为：

```text
Supervisor
  ├─ order_agent      → MCP order Tool / Redis
  ├─ knowledge_agent  → Chroma + 本地 BGE
  ├─ ticket_agent     → interrupt / resume / 审批
  └─ unsupported
```

因此，Starter Kit 适合说明 LangGraph 最小 Tool loop；当前项目保留多领域路由、最小 Tool 权限和写操作 HITL，更贴近企业客服场景。

### 阅读中发现的取舍

模板在 `retrieve` 节点中直接调用 `retrieve_documents`，又把同一函数注册为 LLM 可调用 Tool。这样某些问题可能在模型前检索一次、模型决定调用时又检索一次，造成重复检索、额外延迟和成本。当前项目的 `knowledge_agent` 将检索职责限定在知识领域，更清晰。

## 三、HTTP、Service 与生命周期

模板把 `routers/agents.py` 限制在 HTTP 边界：输入/输出模型、依赖注入、HTTP 错误映射。`AgentService` 承担一次会话调用的应用编排：创建会话、读取历史、组装 `AgentState`、调用 Graph、保存消息、返回 Token 使用量。

```text
HTTP Router
  ↓
AgentService
  ├─ PostgreSQL session/message queries
  ├─ Graph invoke
  └─ structured response
```

这种 Service 层不是“更多耦合”，而是把路由对 SQL 与 Graph State 的耦合集中在一个可替换、可独立测试的层。

其 FastAPI `lifespan` 在启动时配置日志、初始化连接池、编译 Graph；关闭时释放连接池。好处是 Graph 不会随每个请求重新编译，且配置错误会在启动而非第一位用户请求时暴露。

## 四、PostgreSQL、pgvector 与 Alembic

模板用 PostgreSQL 保存 API Key、会话和消息，并启用 pgvector 作为未来向量检索基础。这种单库方案便于事务、备份、迁移和运营，适合早期、数据规模较小且希望减少基础设施数量的产品。

本项目不应因此删除 Redis 或 Chroma：

```text
PostgreSQL → LangGraph Checkpoint / 会话状态
Redis      → 订单查询的短 TTL 缓存
Chroma     → 本地学习型 RAG 向量库
```

三者在本项目中职责明确。未来是否改用 pgvector，应由文档规模、检索性能、运维约束与云部署需求决定，而不是因为某个模板选择了单库。

模板的 Alembic migration 将数据库扩展、表、索引及 `upgrade`/`downgrade` 版本化。它解决“手工建表、不同环境 schema 不一致、启动代码隐式建表”的问题。Stage 12 若新增业务数据表或真实 API Key 表，应借鉴 Alembic；当前 LangGraph Checkpointer 的表由其库管理，不能在不了解其 schema 的情况下随意迁移。

## 五、认证链路和安全审查

Starter Kit 的请求路径：

```text
Authorization: Bearer <key>
  ↓
AuthMiddleware
  ├─ public route 放行
  ├─ ApiKeyService.validate_key()
  ├─ request.state.api_key / tenant_id
  └─ 管理员路径检查 role == admin
  ↓
Router / AgentService
```

相比当前 `.env` 中的单个 `ADMIN_API_TOKEN`，数据库 API Key 可按客户端签发、撤销和记录使用时间，也能携带租户与角色。它适合未来存在真实外部 API 调用方时；当前学习项目暂不需要贸然加入完整身份系统。

### 不应照搬的安全问题

1. 表同时存 `bcrypt key_hash` 与确定性的 SHA-256 `lookup_hash`，但实际 `validate_key()` 仅用 `lookup_hash` 查询，未执行 bcrypt 验证；代码与“bcrypt 用于验证”的注释不一致。
2. API Key 撤销 SQL 只按 `key_id`，未将 `tenant_id` 作为条件；不同租户管理员若获知 ID，可能越权撤销。
3. `agent_sessions` 以 `(session_id, tenant_id)` 唯一，但 `agent_messages` 不保存 `tenant_id`，读取消息只按 `session_id`。相同 `session_id` 跨租户时可能发生串会话。

真实多租户设计应让消息表关联内部 session 主键或显式保存 tenant，并在所有读写 SQL 中带上 tenant 条件。认证不是只验证 Token；还必须在数据查询边界落实授权范围。

## 六、测试、CI 与交付

其 GitHub Actions CI 会：启动 pgvector PostgreSQL 服务、执行 Alembic migration、运行 Ruff、MyPy 与 pytest。`tests/conftest.py` 集中管理环境变量、连接池、Graph 初始化、HTTP Client、测试 API Key 与 Mock LLM，避免每个测试重复准备环境。

这提供三个可借鉴原则：

1. 单元测试 Mock 外部 LLM，避免真实网络、价格和输出波动。
2. 集成测试使用真实数据库，验证迁移和 SQL。
3. CI 在干净环境重复运行静态检查与测试，不能只依赖本机“可以运行”。

模板用 `pyproject.toml` 统一描述项目元数据、Python 版本、运行/开发/生产依赖以及 Ruff、MyPy、Pytest 配置。`Makefile` 为开发者提供 `up`、`migrate`、`dev`、`test`、`lint`、`typecheck` 等统一入口。由于本项目主要在 Windows PowerShell 下学习，不能直接强制照搬 Unix `Makefile`；Stage 12 应选择跨平台脚本或保留清晰的 PowerShell 操作说明。

其生产 Docker 使用 Gunicorn 加多个 Uvicorn worker，而开发模式才使用 `uvicorn --reload`。`--reload` 会监听源码并重启进程，适合编码，不适合不可变镜像的稳定生产运行。

## 最终取舍清单

### 保留当前实现

- PostgreSQL Checkpoint、Redis 订单缓存、Chroma 本地 RAG 的职责分工。
- Supervisor → 订单/知识库/工单领域 Agent 的多 Agent 路由。
- MCP Tool 动态加载与 Human-in-the-Loop 审批。
- `tenant_id` / 会话隔离必须进入数据查询边界的原则。

### 在 Stage 12 选择性借鉴

- Router / Service / Graph 分层，使 HTTP、应用编排和 Agent 定义更清晰。
- `pyproject.toml`、Ruff、MyPy 等项目质量配置。
- CI 中的迁移、Lint、类型检查和测试质量门。
- 针对自有业务表的 Alembic migration。
- 真实外部调用方出现后，再设计多客户端 API Key、租户和角色。

### 不直接照搬

- 因单库简单而用 PostgreSQL/pgvector 全面替换 Chroma 和 Redis。
- 单 Agent `retrieve → model ↔ tools` 取代当前多 Agent/HITL 架构。
- 本模板目前的双 hash API Key 校验和缺少租户条件的撤销/消息查询实现。
- 未调整即用于 Windows 开发工作流的 Unix Makefile。

## 验收标准与证据

```text
已独立 clone 参考仓库；未安装依赖、未运行未知代码。
已阅读 graph State、nodes、tools、graph、routers、service、lifespan。
已阅读 compose、migration、SQL、认证中间件、API Key service、CI、fixtures、pyproject、Makefile、Dockerfile。
已完成项目结构、Graph、数据层、认证、测试、交付五个维度的取舍判断。
已识别三个具体安全/隔离风险，且未把 Starter Kit 当作无条件正确答案。
```

## 面试复盘

1. **为什么不直接 Fork Starter Kit？** 模板解决的是通用单 Agent 后端；本项目的业务差异在 MCP、HITL、缓存和多领域路由。直接替换会抹掉已验证的业务设计。
2. **什么时候考虑 pgvector？** 想减少服务数量、业务数据与向量数据需要事务/关联查询、团队已有 PostgreSQL 运维能力时；而不是因为它在一个模板中出现。
3. **为什么 Router 不直接调用 Graph？** Service 层集中会话加载、状态组装、数据库持久化和调用编排，使 HTTP 层保持薄且更容易测试。
4. **认证通过后为什么仍要在 SQL 加 tenant 条件？** 认证只得到调用者身份；每条数据读写仍需验证该身份对目标数据有权限，避免 ID 碰撞或越权查询。
5. **为什么 CI 要跑 migration？** 代码能通过单元测试不代表空数据库能正确初始化；migration 验证将部署中最常见的 schema 问题提前暴露。

## 阶段复盘

Stage 11 证明了开源 Starter Kit 的正确使用方式：用它学习边界和取舍，而不是复制目录结构或把 README 当作安全保证。当前 Enterprise Support Agent 已拥有清晰的业务特色；下一阶段将独立重构其中值得改善的工程边界，并保留已经验证的多 Agent、MCP、HITL 和分层存储设计。
