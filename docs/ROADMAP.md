# 项目路线图

学习原则：一次只做一个可验证的小步骤。每个阶段结束后才会新增对应的 `docs/phase-notes/` 复盘记录并提交 Git。

| 状态 | 阶段 | 结果 |
|---|---|---|
| 已完成 | Stage 00：项目与开发环境 | 可重复启动、测试和提交的最小项目 |
| 已完成 | Stage 01：单 Agent 与订单 Tool | `/chat → 模型 → Tool → 回答` |
| 已完成 | Stage 02：业务 Tools | 订单、客户、工单与输入/错误契约 |
| 已完成 | Stage 03：RAG | 本地 BGE + Chroma 知识查询、来源与无关问题拒答 |
| 已完成 | Stage 04：MCP | 独立订单 Server、stdio Client、动态 Tool 加载 |
| 已完成 | Stage 05：会话与 Checkpoint | InMemory Checkpoint、thread_id 上下文与隔离 |
| 已完成 | Stage 06：人工审批 | 写操作 interrupt / resume、草稿和幂等正式创建 |
| 已完成 | Stage 07：多 Agent | Supervisor、领域 Agent、最小 Tool 权限与 HITL 继承 |
| 已完成 | Stage 08：持久化与缓存 | Docker PostgreSQL Checkpoint、Redis 缓存、TTL 与失效接口 |
| 已完成 | Stage 09：可靠性与安全 | Trace、JSON 日志、超时、只读重试、结构化响应与输入边界 |
| 未开始 | Stage 10：交付 | Docker、测试、部署与项目演示 |
| 未开始 | Stage 11：开源项目拆解 | 对照 Starter Kit 理解工程取舍 |
| 未开始 | Stage 12：独立重构 | 形成可写入简历的个人版本 |
| 未开始 | Stage 13：面试复盘 | 项目讲解、追问与取舍说明 |

## 每个阶段的固定闭环

1. 明确本阶段唯一目标和不做什么。
2. 拆成 3–8 个小步骤，每步由你操作、我解释和验证。
3. 运行正常路径、错误路径和自动化测试。
4. 我将实际实现、验证命令、结果、问题和你的复盘写入 `docs/phase-notes/`。
5. 检查 Git diff 后提交一条清晰的阶段 commit。
