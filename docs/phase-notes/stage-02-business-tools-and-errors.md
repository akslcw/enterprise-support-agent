# Stage 02：业务 Tool、Schema 与错误处理

## 本阶段目标

将单一订单查询扩展为具有明确输入契约、业务规则和错误边界的 Tool 层，并确保写操作只生成待确认草稿。

## 实际实现

- `app/schemas.py`
  - `CreateTicketInput` 校验客户 ID、标题长度和优先级。
  - `ToolResult` 统一 Tool 成功/失败的返回结构。
- `app/services/tickets.py`
  - `prepare_create_ticket()` 只处理业务规则，不依赖 FastAPI、LangGraph 或模型。
  - 对客户 `blocked` 返回 `CUSTOMER_BLOCKED` 业务错误。
- `app/tools.py`
  - 保留 `get_order_status`。
  - 增加 `prepare_create_ticket`，负责将模型参数转换为 Schema 和 JSON 兼容的 Tool 结果。
- `app/agent.py`
  - Agent 与 ToolNode 共同注册订单查询和工单准备两个 Tool。
  - 系统提示明确：具体问题描述可作为工单标题；工单只能准备、不可宣称已正式创建。

## 分层与原因

```text
模型参数
→ Tool（模型调用入口）
→ Schema（格式与字段约束）
→ Service（业务规则）
→ ToolResult（统一结果）
```

`priority="urgent"` 不属于允许枚举，是输入契约错误，应由 Pydantic 抛出 `ValidationError`。`customer_id="blocked"` 格式合法，但业务规则不允许创建，因此 Service 正常返回 `ToolResult(ok=False, error_code="CUSTOMER_BLOCKED")`。这两类失败不能混淆。

写操作使用 `prepare_create_ticket` 而非 `create_ticket`：当前只返回 `pending_confirmation` 草稿。Stage 06 才会在人工确认后产生真正副作用。

## 验证结果

```powershell
python -m pytest -q
# 结果：9 passed
```

已完成三类手动验证：

1. 自然语言提供客户 ID、问题描述和优先级时，模型生成待确认工单草稿。
2. 明确的结构化请求中，`customer_id="blocked"` 返回用户可理解的业务拒绝与 `CUSTOMER_BLOCKED`。
3. 优化系统提示后，模型将“订单迟迟未送达”正确提取为工单标题，不再重复追问。

## 遇到的问题与处理

初版系统提示要求“明确提供工单标题”，模型将自然语言问题描述误判为标题缺失。提示改为“客户 ID 与明确问题描述即可准备工单，问题描述可作为标题”后，原始自然语言请求成功调用 Tool。这个问题属于模型规划/信息抽取，不是 Schema 或 Service 错误。

## 阶段结论

Stage 02 已完成。下一阶段将引入 RAG：把静态订单/工单规则以外的企业知识通过检索结果提供给模型，并要求回答携带来源或安全拒答。

