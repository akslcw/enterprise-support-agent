# Enterprise Support Agent

一个用于学习 AI 应用开发的企业客服 Agent 项目。项目会按可运行、可验证的阶段逐步实现，而不是一次性堆叠所有框架。

## 当前状态

项目采用“边做边学”的方式重新构建。当前已完成 FastAPI 健康检查、业务 Tool、带来源和拒答边界的本地 RAG，以及通过 MCP Server 动态加载订单查询能力。每个阶段完成并验证后，才会写入真实复盘并提交 Git。

## 目录说明

```text
Enterprise Support Agent/
├─ README.md
├─ app/                                  # FastAPI 服务代码
├─ tests/                                # 自动化测试
├─ requirements.txt                      # 直接依赖
├─ requirements.lock.txt                 # 已验证的精确依赖版本
└─ docs/
   ├─ ROADMAP.md                           # 阶段与当前进度
   ├─ phase-notes/                         # 已完成阶段的真实复盘
   └─ learning-guide/                      # 学习材料与笔记
```

## 从哪里开始

从 [项目路线图](./docs/ROADMAP.md) 的 Stage 00 开始。每完成一个阶段，先验证，再写复盘并提交 Git。
