# Enterprise Support Agent

一个用于学习 AI 应用开发的企业客服 Agent 项目。项目会按可运行、可验证的阶段逐步实现，而不是一次性堆叠所有框架。

## 当前状态

项目采用“边做边学”的方式重新构建。当前已完成 FastAPI 健康检查、业务 Tool、本地 RAG、动态 MCP Tool、基于 `thread_id` 的 Checkpoint 会话记忆与隔离、Human-in-the-Loop 工单审批流，以及由 Supervisor 编排订单、知识库、工单领域 Agent 的 Multi-Agent 架构。会话 Checkpoint 已迁移至 PostgreSQL，订单状态查询已接入 Redis 缓存、TTL 与受保护的失效接口；服务还具备 Trace ID、JSON 结构化日志、超时、只读重试、统一错误契约和输入边界。现在可通过 Docker Compose 启动 app、PostgreSQL 与 Redis，并用独立测试容器验证全套测试。每个阶段完成并验证后，才会写入真实复盘并提交 Git。

## 目录说明

```text
Enterprise Support Agent/
├─ README.md
├─ app/                                  # FastAPI 服务代码
├─ tests/                                # 自动化测试
├─ requirements.txt                      # 直接依赖
├─ requirements.lock.txt                 # 已验证的精确依赖版本
├─ Dockerfile                             # 运行镜像与测试镜像构建目标
├─ compose.yml                            # app、PostgreSQL、Redis 与测试编排
└─ docs/
   ├─ ROADMAP.md                           # 阶段与当前进度
   ├─ phase-notes/                         # 已完成阶段的真实复盘
   └─ learning-guide/                      # 学习材料与笔记
```

## 从哪里开始

从 [项目路线图](./docs/ROADMAP.md) 的 Stage 00 开始。每完成一个阶段，先验证，再写复盘并提交 Git。

## 容器化启动（Stage 10）

本机准备好 `.env`、本地 BGE 模型缓存与 `.chroma` 知识库后，在项目根目录运行：

```powershell
docker compose up -d --build
docker compose ps
docker compose --profile test run --rm test
```

完整准备和排错说明见 [Stage 10 复盘](./docs/phase-notes/stage-10-docker-testing-and-delivery.md)。
