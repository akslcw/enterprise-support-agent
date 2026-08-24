# Stage 03：本地 RAG 知识检索

## 本阶段目标

让企业客服 Agent 能从本地 Markdown 知识库中检索退款政策，并只根据检索到的证据回答；对完全无关的问题不提供编造的答案。

本阶段不做 PDF/OCR、多文档权限、重排序、在线向量库或评估平台。它们会在项目具备稳定最小 RAG 闭环后再逐步加入。

## 最终产物

```text
data/raw/refund-policy.md
        ↓ ingest
切分为带 source 元数据的 chunks
        ↓ BGE embedding
.chroma/ 持久化 Chroma collection
        ↓ retrieve + distance threshold
search_knowledge Tool
        ↓ LangGraph ToolNode
带来源的客服回答 / 无关问题拒答
```

新增目录和职责：

```text
app/rag/
├─ chunker.py       # 读取 Markdown、切分 chunk、保留来源
├─ embeddings.py    # 加载本地中文 BGE，生成归一化向量
├─ store.py         # 建立并写入持久化 Chroma collection
└─ retriever.py     # 查询 collection，筛掉距离过大的结果
data/raw/
└─ refund-policy.md # 当前示例知识文档
scripts/
├─ preview_chunks.py    # 人工检查切分结果
├─ ingest_knowledge.py  # 导入 / 更新向量库
└─ preview_retrieval.py # 人工检查检索结果
```

`.chroma/` 是本地生成的数据，已加入 `.gitignore`；原始 Markdown 文档会提交 Git，方便他人复现知识库。

## 实现步骤与原因

### 1. 把政策写成可版本管理的原始文档

`data/raw/refund-policy.md` 定义了退款时限、数字商品例外、定制商品例外和退款处理时效。知识源必须和代码分开：政策内容变化时，只需改文档并重新入库，不应修改 Agent 图。

### 2. 保留来源地切分文档

`load_markdown_documents()` 把每个 `.md` 转为 LangChain `Document`：

```python
Document(page_content=content, metadata={"source": path.name})
```

`page_content` 是实际参与向量化的文字；`metadata["source"]` 不参与回答推理，但会随 chunk 传递，供最终回答标出 `refund-policy.md`。

`RecursiveCharacterTextSplitter` 使用：

```python
chunk_size=80
chunk_overlap=10
separators=["\n\n", "\n", "。", " ", ""]
```

它优先在段落、换行和句号处切开，最后才按字符兜底。`chunk_overlap=10` 会在相邻块重复少量上下文，避免规则恰好在边界断裂。当前文档很短，因此仍可能看到标题与邻近规则一起出现；这不是全文返回，而是为了保留语义边界。

### 3. 使用本地中文 Embedding 模型

默认 Chroma 模型以英文场景为主，因此使用本机已有的 `BAAI/bge-small-zh-v1.5`：

```python
SentenceTransformer(MODEL_NAME, local_files_only=True)
```

`local_files_only=True` 保证运行时不意外下载模型。`normalize_embeddings=True` 将向量归一化，使 Chroma 的 cosine 距离可用于同一 collection 内的相对比较。

首次实现时，单次脚本运行会多次出现 `Loading weights`。原因是 Chroma 可能重建自定义 embedding function；只缓存 function 不足以保证模型实例复用。最终将模型加载函数也加上 `@lru_cache(maxsize=1)`：

```python
@lru_cache(maxsize=1)
def get_bge_model() -> SentenceTransformer:
    return SentenceTransformer(MODEL_NAME, local_files_only=True)
```

这保证同一 Python 进程只加载一次模型。每次重新执行命令会启动新的进程，因此重新加载一次是正常现象。

### 4. 使用持久化向量库，并允许重复导入

`PersistentClient(path=".chroma")` 让向量在脚本退出后继续存在。chunk ID 采用：

```python
f"{source}:{index}"
```

写入时使用 `collection.upsert()`，而不是 `add()`。因此重复运行 `python -m scripts.ingest_knowledge` 不会把相同 ID 的 chunk 反复累积。实际验证中两次入库后，collection 总数都为 `2`（当时的切分配置）。

### 5. 检索与 Top-K

`search_knowledge(query, limit=2)` 中的 `limit` 就是 Top-K：从所有 chunk 取距离最小的前 K 个。它不控制每个 chunk 的大小。

```text
chunk_size：每段原文有多大
chunk_overlap：相邻段共享多少上下文
limit / Top-K：一次交给后续步骤几段候选证据
distance：问题向量与 chunk 向量的距离，当前 collection 内越小通常越相关
```

仅有 Top-K 不代表结果真的相关：任何问题都能找到“最接近”的 chunk。因此 `retriever.py` 增加了当前数据集校准得到的初版阈值：

```python
MAX_DISTANCE = 0.50

if distance > max_distance:
    continue
```

实测数据如下：

| 问题 | Top-1 距离 | 结果 |
|---|---:|---|
| `退款审核通过后多久到账？` | 0.3252 | 命中退款处理时效 |
| `未使用的数字商品可以退款吗？` | 0.2613 | 语义相关，但原文未覆盖完整条件 |
| `北京今天天气怎么样？` | 0.7857 | 过滤为无资料 |

`0.50` 只适用于当前 BGE、当前 collection 和当前资料；新增文档、更换模型或调整切分后，必须重新用一组带标签的问题校准，不能把它当成通用常量。

### 6. 通过 Tool 接入现有 LangGraph

`app/tools.py` 的 `@tool search_knowledge(question)` 调用 retriever，把每个命中项组织为：

```text
证据 1
来源：refund-policy.md
内容：...
```

Agent 与 `ToolNode` 注册同一组 Tools：

```python
tools = [get_order_status, prepare_create_ticket, search_knowledge]
model = create_chat_model().bind_tools(tools)
builder.add_node("tools", ToolNode(tools))
```

图结构没有因为 RAG 改变：模型仍决定是否调用 Tool，`ToolNode` 执行 Tool，Tool 结果作为消息回到模型。RAG 是一个可替换的业务能力，而不是第二套 Agent 图。

## 重要安全边界

首次测试“数字商品可以退款吗？”时，模型依据两段资料给出“未使用的数字商品可在 7 天内退款”。这句话看似合理，但原文没有明确把“未使用的数字商品”和“7 天规则”关联起来，因此是不被允许的推断。

系统提示随后补充三层约束：

1. 不同段落的条件不得自行拼接成新规则。
2. 文档未明确覆盖的条件，必须说明“当前资料未说明”。
3. 天气、新闻等企业客服范围外的问题不得用模型自身常识回答。

因此：

```text
距离阈值：拦截完全无关的问题。
提示词证据规则：拦截“看似相关但没有充分证据”的推断。
两者缺一不可。
```

## 验证记录

自动化测试使用项目虚拟环境运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
# 结果：15 passed
```

测试覆盖：

- Markdown 文档加载时保留 `source` 元数据。
- 切分后仍保留全部退款规则。
- retriever 将 Chroma 的嵌套结果整理为统一字典结构。
- `distance=0.7857` 的候选会被阈值过滤。
- Tool 在有证据时带回来源和正文；无证据时返回统一提示。

已完成的手动集成验证：

1. 重复导入知识后，向量库 chunk 总数没有重复累积。
2. “数字商品可以退款吗？”触发 `search_knowledge`，回答包含 `refund-policy.md`，并明确未知部分。
3. “北京今天天气怎么样？”在检索脚本中显示“知识库中没有足够相关的资料”。
4. 相同天气问题经 `/chat` 返回“当前服务不支持该问题”，没有输出天气事实或退款政策。

一次容易误判的环境问题：直接调用系统 `python -m pytest` 会因系统解释器未安装项目依赖而报 `ModuleNotFoundError`。这不是项目失败；应始终激活 `.venv` 后运行，或显式使用 `.\.venv\Scripts\python.exe`。

## 阶段验收标准

- [x] 本地 Markdown 能切分、保留来源并写入持久化 Chroma。
- [x] 使用本地中文 BGE，且同一进程内只加载一次模型。
- [x] 相关问题能取回政策原文和来源。
- [x] 无关天气问题被距离阈值过滤。
- [x] LangGraph Agent 可以选择并调用知识 Tool。
- [x] 回答不会把不同规则擅自组合成文档未写出的结论。
- [x] 项目虚拟环境下自动化测试全部通过。

## 面试复盘

**问：LangChain、Chroma、BGE、LangGraph 分别负责什么？**

`Document` 和 `RecursiveCharacterTextSplitter` 来自 LangChain 生态，用于统一文档对象和切分；BGE 把文本转为向量；Chroma 保存与相似度检索向量；LangGraph 编排“模型选择 Tool → Tool 执行 → 模型回答”的循环。它们不是互相替代关系。

**问：为什么不能只让模型直接读整个退款文档？**

小文档可以，但文档规模增长后上下文成本、更新难度、噪声和引用可追溯性都会变差。RAG 先筛出少量证据，再让模型回答；但仍须防止模型过度推断。

**问：为什么需要阈值？**

向量检索永远能返回“最相近”的文本，即使问题完全无关。阈值让系统有“没有合格证据”的分支。

**问：阈值能解决所有幻觉吗？**

不能。`未使用数字商品是否退款` 的距离很小，却仍缺少明确规则。阈值处理相关性，提示词、结构化规则、人工流程和评估集处理证据充分性。

## 扩展练习

1. 新增一份 `shipping-policy.md`，重新入库并验证来源正确显示。
2. 为每个 chunk 增加 `document_type`、`updated_at` 元数据，并按元数据过滤检索。
3. 为 10 个已知问题手工标记“应命中 / 应拒答”，比较不同 `chunk_size`、Top-K 和阈值的效果。
4. 将 Tool 输出改为 JSON 结构，下一阶段前比较“纯文本证据”和“结构化证据”对模型引用准确性的影响。

## 阶段结论

Stage 03 已完成最小可验证的本地 RAG 闭环。下一阶段将把一部分 Tool 能力抽离为 MCP Server，使 Agent 通过标准协议发现并调用外部能力，而不是只依赖进程内 Python 函数。
