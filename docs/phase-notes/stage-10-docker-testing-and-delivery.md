# Stage 10：Docker、测试与交付准备

## 本阶段目标

把此前只能依赖本机虚拟环境启动的 Enterprise Support Agent，变成可由 Docker Compose 一致启动和验证的服务。交付不只意味着“容器能启动”，还必须验证：应用能连接 Compose 网络中的 PostgreSQL 与 Redis、本地 BGE 模型在容器中可用、MCP 子进程能被容器正确启动，以及自动化测试能在独立测试容器中通过。

本阶段不做公网部署、CI/CD、镜像仓库发布或 Kubernetes。这些将在项目稳定后作为部署练习继续处理。

## 最终交付结构

```text
Docker Compose
├─ app                 # FastAPI + LangGraph + MCP Client + BGE/Chroma
│  ├─ POSTGRES_HOST=postgres
│  └─ REDIS_HOST=redis
├─ postgres            # LangGraph PostgreSQL Checkpointer
├─ redis               # 订单查询缓存
└─ test（profile=test）# 在隔离容器内执行 pytest
```

`app` 不再从宿主机的 `.venv` 路径启动 MCP Server。`app/mcp_client.py` 使用 `sys.executable`，即“当前正在运行应用的 Python 解释器”：宿主机运行时是虚拟环境 Python，Docker 中运行时是容器 Python。这样同一份代码才能跨平台、跨运行环境工作。

## 关键文件与职责

```text
Dockerfile                     # 运行镜像与 test 构建目标
.dockerignore                  # 排除 Git、.venv、密钥和无关构建上下文
compose.yml                    # app、PostgreSQL、Redis、test profile 的编排
.env.example                   # 新增 APP_PORT 的可复制环境变量模板
app/mcp_client.py              # 使用 sys.executable 生成 MCP 启动配置
tests/test_mcp_client_config.py# 验证 MCP 配置不依赖 Windows .venv 硬编码路径
```

运行镜像的核心约束：

1. 以 `python:3.13-slim` 为基础镜像，安装 `requirements.txt`。
2. 用 Docker BuildKit 的 pip cache 减少重复下载；网络发生临时中断时允许有限重试和较长超时。
3. 拷贝 `app/`、`mcp_servers/`、`data/` 与本地 Chroma 数据目录。
4. 拷贝本地 Hugging Face BGE 缓存到 `/opt/huggingface`，并通过 `HF_HOME` 使 `local_files_only=True` 在容器中也能加载模型。
5. 使用非 root 用户 `appuser` 运行应用。
6. 仅把 `127.0.0.1:${APP_PORT}` 映射到宿主机，避免学习环境中的服务被局域网直接访问。
7. 以 `/health` 作为容器 health check。

## 本地模型与数据资产

RAG 仍然使用 `BAAI/bge-small-zh-v1.5` 与本地 Chroma 目录。它们属于可再生成或体积较大的本机资产，因此：

```text
models/   # Hugging Face 模型缓存：.gitignore，Docker 构建时读取
.chroma/  # 本地向量库：.gitignore，Docker 构建时读取
```

第一次在另一台机器构建前，必须先准备本地 BGE 缓存（或调整 Embedding 实现允许受控下载），并先执行知识库导入生成 `.chroma`。不应把模型权重、向量库或 `.env` 提交到 GitHub。

## 启动与验证手册

在项目根目录执行：

```powershell
docker compose up -d --build
docker compose ps
```

验收时 `app`、`postgres`、`redis` 都应为 `healthy`。应用在 Compose 内部通过服务名 `postgres` 和 `redis` 连接基础设施，而不是使用宿主机的 `127.0.0.1`。

验证健康接口：

```powershell
Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/health
```

验证完整订单链路时，可以调用 `/chat` 并附带 `X-Trace-ID`，再查看日志：

```powershell
docker compose logs app --tail 100
```

预期日志中能按 Trace ID 找到 `http_request_completed`，并能看到 MCP 对 `order_get_status` 的调用。这证明请求并不只是通过健康检查，而是实际经过 FastAPI、Supervisor/LangGraph、MCP 和业务 Tool。

验证容器内离线 BGE：

```powershell
docker run --rm --entrypoint python enterprise-support-agent:stage10 -c "from app.rag.embeddings import get_bge_model; model = get_bge_model(); print(model.__class__.__name__)"
```

预期输出为 `SentenceTransformer`。若失败，优先检查 `models/huggingface` 是否存在、Dockerfile 是否复制到 `/opt/huggingface`，以及 `HF_HOME` 是否设置。

运行容器化测试：

```powershell
docker compose --profile test run --rm test
```

`test` 服务采用 Compose profile，因此普通 `docker compose up -d` 不会启动它。该服务复用同一个构建上下文，但以 Dockerfile 的 `test` target 执行 `python -m pytest -q`。

## 实际验证证据

```text
本地 MCP 配置测试：2 passed
本机完整测试：122 passed
运行镜像构建：成功（enterprise-support-agent:stage10）
容器内 BGE 加载：成功（SentenceTransformer）
Compose 运行：app、postgres、redis 均 healthy
容器真实 /chat：HTTP 200，Trace ID 成功写入应用日志，MCP Tool 被调用
测试容器：122 passed in 9.20s
```

构建期间曾遇到 Docker Desktop 在最后“unpacking”测试镜像时返回 EOF。Docker 层与 manifest 已完成，问题发生在 Docker Desktop 后端通信；重启并恢复引擎后重新运行测试成功。因此这不是 Python 依赖、Dockerfile 或测试用例的失败。

## 常见错误与调试

| 现象 | 常见原因 | 处理方式 |
|---|---|---|
| Dockerfile 报 `Unknown instruction: "UVICORN"` | JSON 形式 `CMD` 被错误地分行书写 | 保持为单行合法 JSON 数组 |
| `pip install` 报 `IncompleteRead` | 构建时网络临时中断 | 使用 BuildKit pip cache、重试与超时；重试构建，不要改业务依赖掩盖网络问题 |
| BGE 下载超时 | 容器构建时依赖外网下载模型 | 使用已验证的本地 Hugging Face 缓存，并设置 `HF_HOME` |
| 容器中 MCP 无法启动 | 写死了宿主机 `.venv\\Scripts\\python.exe` | 使用 `sys.executable`，并以模块形式执行 `-m mcp_servers.order_server` |
| `app` 无法连数据库或 Redis | Compose 内仍配置 `127.0.0.1` | app 服务中覆盖为 `postgres`、`redis` 服务名 |
| PowerShell 输出中文乱码 | 终端编码显示问题 | 以 HTTP 200、响应 JSON、容器日志和 Trace ID 判断服务；必要时设置终端为 UTF-8 |
| Docker `EOF` 或状态命令无响应 | Docker Desktop 后端暂时断开 | 确认 Docker Engine 为 Running 后再检查镜像并重跑；不要盲目清理镜像或 volume |

## 面试要点

1. **为什么 Docker 中不能继续使用本机 Python 路径？** 镜像文件系统与 Windows 宿主机隔离，`E:\\...\\.venv\\Scripts\\python.exe` 在 Linux 容器中不存在；`sys.executable` 能随运行环境自动选择解释器。
2. **为什么 app 在 Compose 中连接 `postgres` 而不是 `localhost`？** `localhost` 指向当前 app 容器本身；Compose 自动提供以服务名为 DNS 名称的内部网络。
3. **为什么测试服务要使用 profile？** 开发或演示启动时不应额外运行一次测试；需要验证时才显式 `--profile test` 启动一次性任务。
4. **为什么模型和 Chroma 数据不提交 Git？** 它们体积大、可再生成，并可能随机器或知识库变化；代码库应记录构建方式和准备步骤，而不是把机器缓存当作源码。
5. **Docker health check 与端口可访问有什么区别？** 端口可访问只说明进程可能在监听；health check 表示容器内部探针成功，Compose 可以据此控制依赖启动顺序。

## 阶段复盘

Stage 10 的核心不是“把 Python 放进容器”，而是消除隐式环境假设：解释器不能写死、本地模型要有明确来源、服务间连接必须通过容器网络、测试也应在接近交付环境中执行。现在该项目具备可重复启动、可验证和可演示的本地交付形态。

下一阶段将选择一个开源 Agent Starter Kit，与当前实现逐层对照，理解哪些能力应保留、替换或简化。
