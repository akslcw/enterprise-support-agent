# Stage 04：MCP 独立订单工具服务

## 本阶段目标

把订单状态查询从 Agent 进程内的 LangChain Tool 拆为独立 MCP Server，并让 FastAPI 在启动时发现 MCP Tool、创建异步 LangGraph，然后在 `/chat` 中通过 MCP 查询订单。

本阶段只实现本地 `stdio` 传输和一个只读订单 Tool；不做远程 HTTP、认证、多 Server、写操作或服务部署。

## 最终调用链

```text
POST /chat
  ↓
FastAPI lifespan（应用启动时只执行一次）
  ↓
load_mcp_tools()
  ↓ stdio / JSON-RPC
mcp_servers.order_server 子进程
  ↓ tools/list
order_get_status 被转换为 LangChain Tool
  ↓
create_graph(mcp_tools)
  ↓ 请求期间 graph.ainvoke()
LLM 选择 order_get_status
  ↓ ToolNode
MCP Client → MCP Server → app.services.orders
  ↓
结构化订单结果 → LLM → 最终客服回答
```

## 新增结构与职责

```text
app/
├─ mcp_client.py          # Server 启动命令、stdio 配置和动态 Tool 发现
└─ services/orders.py     # 与框架无关的订单查询业务逻辑
mcp_servers/
├─ __init__.py            # 允许以 python -m 方式启动
└─ order_server.py        # MCP Server：公开 order_get_status
scripts/
└─ inspect_mcp_server.py  # 独立 Client 发现和调用 MCP Tool
tests/
├─ test_order_service.py      # 订单领域逻辑
└─ test_mcp_order_server.py   # MCP Tool 的结构化返回契约
```

`app/tools.py` 不再包含 `get_order_status`。订单查询的唯一 Agent 入口是 MCP Server 的 `order_get_status`，避免本地和远程两份实现逐渐漂移。

## 设计与实现

### 1. 先抽取框架无关的 Service

`app/services/orders.py` 的 `lookup_order_status()` 只处理 mock 订单数据，返回稳定契约：

```python
{
    "order_id": "1002",
    "found": True,
    "status": "运输中，预计明天送达",
}
```

它不导入 FastAPI、LangGraph、LangChain 或 MCP。因此本地 API、MCP Server 和未来数据库实现都可以复用它。

`found=False` 是成功的业务结果，不是传输错误：

```text
McpError / Connection closed：进程、协议或依赖失败。
found: false：协议调用已成功，但不存在该订单。
```

### 2. 使用本地 stdio MCP Server

`mcp_servers/order_server.py` 使用 MCP 1.x 的 `FastMCP`：

```python
mcp = FastMCP(name="order_mcp")

@mcp.tool(name="order_get_status", structured_output=True)
def order_get_status(order_id: str) -> OrderStatusResponse:
    return OrderStatusResponse(**lookup_order_status(order_id))
```

`stdio` 意味着 MCP Client 启动 Server 子进程，并经由标准输入输出传输 JSON-RPC。Server 的 stdout 只能放协议消息，不能使用 `print()` 调试；日志可输出至 stderr。

选择 stdio 的原因：当前是单机学习环境、没有网络监听端口、配置简单。以后多个客户端或远程部署时，再使用 Streamable HTTP，并增加认证、Origin 校验和本地绑定等安全措施。

Tool 使用 `order_` 前缀，是为了未来与 `ticket_*`、`knowledge_*` 等多个 Server 同时连接时避免重名。Tool annotations 声明它是只读、非破坏、可重复调用且不访问开放外部世界；这些是客户端提示，不是权限系统。

### 3. 结构化输出使用 Pydantic，而不是裸 dict

首次实现中，函数返回标注为 `-> dict` 且启用了 `structured_output=True`。MCP 1.29.1 在 Server 注册 Tool 时报告：

```text
InvalidSignature: return type <class 'dict'> is not serializable
for structured output
```

修复是定义 `OrderStatusResponse(BaseModel)`，明确 `order_id`、`found`、`status` 的字段类型和含义。Pydantic 模型可被转换为稳定 JSON Schema；裸 `dict` 只说明“有一个字典”，没有可验证的输出契约。

### 4. 以模块方式启动 Server

最初 Client 的 `args` 是脚本文件路径，导致 Server 子进程的模块搜索路径只有 `mcp_servers/`，无法导入同级 `app/`，最终表现为 Client 侧笼统的：

```text
McpError: Connection closed
```

实际根因是 Server stderr 中的：

```text
ModuleNotFoundError: No module named 'app'
```

修复方式是创建 `mcp_servers/__init__.py`，并让 Client 用模块方式启动：

```python
"args": ["-m", "mcp_servers.order_server"]
```

`cwd` 只决定当前工作目录，不等于 Python 自动把项目根目录加入 import path；`python -m` 才使项目根目录成为模块起点。

### 5. 显式管理 SDK 版本兼容性

最初安装的最新组合为 `mcp 2.1.0` 与 `langchain-mcp-adapters 0.3.1`。虽然 pip 没有报冲突，但 Adapter 导入 MCP 1.x 的 `RequestContext`，导致：

```text
ImportError: cannot import name 'RequestContext'
```

项目改为经过验证的组合：

```text
mcp[cli]>=1.29.1,<2
langchain-mcp-adapters>=0.3.1,<0.4
```

这说明依赖解析成功不等于运行时兼容。`requirements.txt` 用上限阻止下一次安装时悄悄升级到不兼容的 MCP 2.x；`requirements.lock.txt` 记录本次实际验证版本。

### 6. 为什么 Agent 变为异步

`load_mcp_tools()` 要等待子进程启动、MCP 初始化和 `tools/list`；每一次远程 Tool 调用也要等待 stdio I/O。它们是外部 I/O，使用 `await` 时不会阻塞 FastAPI 事件循环。

执行顺序有依赖，并非并行：

```python
mcp_tools = await load_mcp_tools()
app.state.graph = create_graph(mcp_tools)
```

先发现 Tool，后创建绑定 Tool 的 Graph。请求处理同样使用：

```python
result = await request.app.state.graph.ainvoke(...)
```

异步的价值是等待 MCP 或 LLM 的期间，服务仍能处理其他协作任务；不是让“未发现 Tool 的 Graph”先开始编排。

### 7. FastAPI lifespan 与动态 Tool 加载

`app/main.py` 使用 `lifespan`：应用启动时加载一次 MCP Tool，调用 `create_graph(mcp_tools)`，并把 Graph 放在 `app.state.graph`。因此每个 `/chat` 请求不会重复 tools/list，也不会重复构建 Graph。

`ToolNode` 同时可包含同步的本地 Tool（工单准备、RAG）与异步的 MCP Tool；Graph 必须以 `ainvoke()` 运行，才能等待远程 Tool 执行完成。

## 验证结果

自动化验证：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 结果：17 passed
```

独立 MCP Client 验证发现以下 Tool：

```text
order_get_status: 根据订单编号查询订单当前状态。仅查询，不创建或修改订单。
```

手动调用 `1002` 返回：

```json
{"order_id": "1002", "found": true, "status": "运输中，预计明天送达"}
```

手动调用 `9999` 返回：

```json
{"order_id": "9999", "found": false, "status": null}
```

LangGraph 检查消息序列为：

```text
human
→ ai tool_call: order_get_status
→ tool: MCP 返回的订单结构化内容
→ ai: “运输中，预计明天送达”
```

最后已在 FastAPI `/chat` 完成订单存在与不存在两种端到端验证。

## 阶段验收标准

- [x] 订单领域逻辑可脱离 Agent 和 MCP 单独测试。
- [x] MCP Server 通过 stdio 被 Client 启动。
- [x] Client 能动态发现 `order_get_status`。
- [x] 已验证存在与不存在订单的结构化返回。
- [x] FastAPI 启动时加载 MCP Tool，Graph 以异步方式执行。
- [x] LangGraph 的订单查询实际调用 MCP Tool，而非旧本地 Tool。
- [x] 项目虚拟环境中自动化测试全部通过。

## 常见错误与调试方法

| 表现 | 根因 | 检查与处理 |
|---|---|---|
| `Connection closed` | Server 子进程已崩溃 | 直接以同一个 Python 命令启动 Server，查看 stderr 的最底层异常 |
| `No module named app` | 把 Server 当文件运行 | 加 `__init__.py` 并使用 `python -m mcp_servers.order_server` |
| `InvalidSignature` | `structured_output=True` 却返回裸 dict | 改用 Pydantic 输出模型 |
| Adapter import 报错 | MCP 2.x 与当前 Adapter 不兼容 | 使用 requirements 中锁定的 MCP 1.x 范围 |
| 中文乱码 | Windows 子进程编码与 stdio UTF-8 不一致 | MCP 子进程配置 `PYTHONUTF8=1` |

## 面试复盘

**问：MCP 和 LangGraph 分别解决什么问题？**

MCP 定义 Agent Host/Client 与工具服务之间发现和调用工具的标准协议；LangGraph 负责应用内部状态、节点和 Tool 调用循环。MCP 可以是 LangGraph 的 Tool 来源，但两者不是替代关系。

**问：为什么不直接在 Agent 中保留 Python 函数？**

本地函数最简单，但工具实现与 Agent 进程强耦合。MCP 可独立运行、可被多个 Host 复用，并能在不修改 Agent 图核心逻辑的前提下增加新的 Tool 服务。

**问：为什么选择 stdio？**

本地、单用户、开发环境选 stdio，Client 管理 Server 子进程且不暴露网络端口。远程和多客户端场景选 Streamable HTTP，并需要认证、Origin 检查与网络安全配置。

**问：为什么 API 和 Graph 都改成 async？**

模型调用和 MCP 传输都属于等待型 I/O。异步使请求等待期间不阻塞事件循环；启动时仍严格遵守“先加载 Tool、再建 Graph”的依赖顺序。

## 扩展练习

1. 新增 `order_list_recent_orders`，实现 `limit`、`offset` 和分页元数据。
2. 新增独立 Ticket MCP Server，并让 Client 同时发现两个 Server 的 Tool。
3. 将 Server 改为 Streamable HTTP，仅绑定 `127.0.0.1`，并验证 MCP endpoint。
4. 给 MCP Tool 增加请求耗时日志，下一阶段再将 trace ID 贯穿 FastAPI、Graph 和 Server。

## 阶段结论

Stage 04 已完成。下一阶段将引入 LangGraph Checkpoint、thread_id 和 Session 隔离：同一个用户会话能够保留上下文，不同用户或不同 thread 的消息不会串线。
