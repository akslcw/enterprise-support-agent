# Stage 00：环境与健康检查

## 本阶段目标

在正确的项目目录中建立独立 Python 环境，并运行一个可自动测试、可由浏览器访问的 FastAPI 服务。

## 实际完成内容

- 项目根目录：`E:\code\ai_agent\work\Enterprise Support Agent`
- Python：3.13.5
- 虚拟环境：`.venv\Scripts\python.exe`
- 直接依赖：FastAPI、Uvicorn、pytest、httpx
- 服务入口：`app/main.py`
- 健康检查：`GET /health` 返回 `{"status":"ok"}`
- 自动化测试：`tests/test_health.py`
- 精确依赖快照：`requirements.lock.txt`

## 关键概念

`app` 是 FastAPI 应用对象。`@app.get("/health")` 将 HTTP GET 请求绑定到 `health()` 函数；该函数返回的字典由 FastAPI 编码成 JSON。

测试中的 `TestClient(app)` 不启动 8000 端口，而是在 Python 进程内模拟 HTTP 请求。它断言状态码为 200、JSON 内容为 `{"status":"ok"}`，因此能在不打开浏览器的情况下检查路由是否回归。

## 验证证据

```powershell
python -m pytest -q
# 结果：1 passed

python -m uvicorn app.main:app --reload
# 浏览器访问 /health：{"status":"ok"}
```

## 遇到的问题与处理

直接执行 `pytest -q` 时，VS Code 的运行配置没有正确把项目根目录加入导入路径，出现 `ModuleNotFoundError: app`。使用已选中的项目虚拟环境并运行 `python -m pytest -q` 后通过。今后统一以 `python -m ...` 运行 pip、pytest 和 uvicorn，避免错误使用全局解释器。

## 阶段结论

Stage 00 已完成。下一阶段开始前，工作区必须保持干净；Stage 01 将先实现不依赖模型 API 的订单查询 Tool，并为它写测试。

