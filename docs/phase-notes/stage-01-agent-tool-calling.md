# Stage 01：单 Agent 与订单查询 Tool

## 本阶段目标

实现最小 Agent 闭环：`POST /chat → DeepSeek 决策 → 订单 Tool → DeepSeek 最终回答`。

## 实际实现

- `app/llm.py`：从 `.env` 读取模型名、API Key 和 OpenAI 兼容接口地址，创建聊天模型。
- `app/tools.py`：`get_order_status(order_id)` 使用 mock 订单数据返回确定性业务结果。
- `app/agent.py`：用 LangGraph 构建 `START → agent → tools → agent → END`。
- `app/main.py`：增加 `POST /chat`；输入通过 Pydantic 校验后转为 `HumanMessage` 并交给 Graph。
- `scripts/check_model.py`：独立检查模型连通性。
- `scripts/inspect_graph_run.py`：打印一次完整图运行的内部消息序列。

## 关键设计

模型只决定是否调用工具和如何组织回答；它不直接运行 Python。`ToolNode` 是执行 `get_order_status` 的确定性节点。`AgentState.messages` 通过 `add_messages` 追加人类消息、模型工具请求、Tool 结果和最终回复，因此每个节点都能读取必要上下文。

模型通过 `bind_tools([get_order_status])` 获得工具 Schema。模型提出 `tool_calls` 时，`tools_condition` 将图路由到 `tools`；没有 Tool 调用时直接结束。Tool 节点执行后回到 agent 节点，使模型基于真实结果回答。

## 验证结果

自动化测试：

```powershell
python -m pytest -q
# 结果：3 passed
```

真实接口请求：

```json
{"message":"订单 1002 到哪里了？"}
```

得到的最终答复说明订单正在运输中、预计明天送达。

内部消息顺序验证：

```text
1. human：订单 1002 到哪里了？
2. ai：tool_calls = get_order_status(order_id="1002")
3. tool：运输中，预计明天送达
4. ai：面向用户的最终自然语言答复
```

## 遇到的问题与处理

直接使用 `python scripts/inspect_graph_run.py` 时，Python 将 `scripts/` 作为首要导入位置，导致找不到同级 `app/` 包。创建 `scripts/__init__.py` 后，使用 `python -m scripts.inspect_graph_run` 以项目模块方式运行，导入路径正确。

## 阶段结论

Stage 01 已完成。当前订单数据仍是 mock，不含会话记忆和写操作。Stage 02 将扩展多个业务 Tool，并建立输入 Schema、错误码和业务错误边界。

