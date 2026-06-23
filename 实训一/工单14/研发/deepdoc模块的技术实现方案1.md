# DeepDoc 模块的技术实现方案 — 分块策略与任务队列机制

> **分析范围**：当解析文件为 PDF 时，`parser_id` 为 `paper`、`table`、`one`、`knowledge_graph` 四种分块策略的触发机制、解析任务如何放入 Redis Stream 消息队列、以及任务执行器如何消费和处理  
> **代码位置**：`ragflow-main/`（api、rag、deepdoc 目录）  
> **文档生成时间**：2026年6月

---

## 目录

- [一、整体架构与数据流概览](#一整体架构与数据流概览)
- [二、PDF 解析任务的创建与触发](#二pdf-解析任务的创建与触发)
  - [2.1 用户触发入口](#21-用户触发入口)
  - [2.2 queue_tasks() 任务拆分逻辑](#22-queue_tasks-任务拆分逻辑)
  - [2.3 四种 parser_id 的任务分片规则对比](#23-四种-parser_id-的任务分片规则对比)
- [三、Redis Stream 消息队列机制](#三redis-stream-消息队列机制)
  - [3.1 任务推入队列（生产者）](#31-任务推入队列生产者)
  - [3.2 任务消费（消费者）](#32-任务消费消费者)
  - [3.3 消息确认与可靠性保证](#33-消息确认与可靠性保证)
- [四、四种 parser_id 的分块策略深度分析](#四四种-parser_id-的分块策略深度分析)
  - [4.1 FACTORY 分块器注册表](#41-factory-分块器注册表)
  - [4.2 paper（论文分块）](#42-paper论文分块)
  - [4.3 table（表格分块）](#43-table表格分块)
  - [4.4 one（整文档一块）](#44-one整文档一块)
  - [4.5 knowledge_graph（知识图谱分块）](#45-knowledge_graph知识图谱分块)
- [五、build_chunks() 统一分块执行流程](#五build_chunks-统一分块执行流程)
- [六、do_handle_task() 完整处理管线](#六do_handle_task-完整处理管线)
- [七、DeepDoc PDF 解析管线（底层引擎）](#七deepdoc-pdf-解析管线底层引擎)
- [八、完整流程图总结](#八完整流程图总结)

---

## 一、整体架构与数据流概览

```
┌──────────────────────────────────────────────────────────────────────────┐
│                     PDF 文档解析完整数据流                                │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  用户点击"解析"                                                           │
│       │                                                                  │
│       ▼                                                                  │
│  ┌─────────────────────────────────┐                                    │
│  │  api/apps/document_app.py       │                                    │
│  │  run() → DocumentService.run()  │                                    │
│  └──────────────┬──────────────────┘                                    │
│                 │                                                         │
│                 ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐            │
│  │  api/db/services/task_service.py :: queue_tasks()       │            │
│  │                                                         │            │
│  │  ① 根据 parser_id 确定 page_size                        │            │
│  │     ├── paper        → 22 页/任务                       │            │
│  │     ├── table        → 3000 行/任务（Excel）             │            │
│  │     ├── one          → 整个文档（10^9）                  │            │
│  │     └── knowledge_graph → 整个文档（10^9）               │            │
│  │                                                         │            │
│  │  ② 按 page_size 拆分为多个 parse_task                   │            │
│  │                                                         │            │
│  │  ③ 计算任务摘要（digest）用于去重和复用                   │            │
│  └──────────────┬──────────────────────────────────────────┘            │
│                 │                                                         │
│                 ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐            │
│  │  Redis Stream（XADD）                                   │            │
│  │  队列名: rag_flow_svr_queue (优先级0)                    │            │
│  │         rag_flow_svr_queue_1 (优先级1)                   │            │
│  └──────────────┬──────────────────────────────────────────┘            │
│                 │                                                         │
│                 ▼                                                         │
│  ┌─────────────────────────────────────────────────────────┐            │
│  │  rag/svr/task_executor.py                               │            │
│  │                                                         │            │
│  │  collect() ← XREADGROUP 消费任务                        │            │
│  │       │                                                 │            │
│  │       ▼                                                 │            │
│  │  do_handle_task()                                       │            │
│  │       │                                                 │            │
│  │       ├── build_chunks()                                │            │
│  │       │     └── FACTORY[parser_id].chunk()              │            │
│  │       │         ├── paper.chunk()    → 论文分块         │            │
│  │       │         ├── table.chunk()    → 表格分块         │            │
│  │       │         ├── one.chunk()      → 整文档一块       │            │
│  │       │         └── naive.chunk()    → 通用分块(KG)     │            │
│  │       │                                                 │            │
│  │       ├── embedding()                                   │            │
│  │       └── insert_chunks()                               │            │
│  └─────────────────────────────────────────────────────────┘            │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 二、PDF 解析任务的创建与触发

### 2.1 用户触发入口

用户在 Web UI 点击文档的"解析"按钮，触发请求链路：

```python
# api/apps/document_app.py (lines 615-672)
@app.route('/run', methods=['POST'])
def run():
    """
    路由: POST /api/v1/document/run
    接收参数: doc_ids (文档ID列表), run (运行状态)
    """
    for doc_id in doc_ids:
        # 1. 检查文档访问权限
        # 2. 更新文档状态为"解析中"
        # 3. 清除旧的 chunks（如果重新解析）
        # 4. 调用 DocumentService.run() 触发任务入队
        DocumentService.run(tenant_id, doc_dict, kb_table_num_map)
```

`DocumentService.run()` 最终调用 `task_service.py` 中的 `queue_tasks()` 函数，这是任务创建的核心。

### 2.2 queue_tasks() 任务拆分逻辑

**文件**：`api/db/services/task_service.py`（第 360-464 行）

该函数是整个任务调度的起点，核心逻辑分为三步：**确定分片大小 → 拆分任务 → 推入队列**。

#### Step 1：根据 parser_id 确定 page_size

```python
# api/db/services/task_service.py (lines 393-424)

if doc["type"] == "pdf":
    pages = PdfParser.total_page_number(doc["name"], file_bin)
    
    # 默认：12 页/任务
    page_size = doc["parser_config"].get("task_page_size") or 12
    
    # paper 解析器：22 页/任务（更大的上下文窗口）
    if doc["parser_id"] == "paper":
        page_size = doc["parser_config"].get("task_page_size") or 22
    
    # one / knowledge_graph / 非DeepDOC / 启用TOC → 整个文档作为一个任务
    if (doc["parser_id"] in ["one", "knowledge_graph"] 
        or do_layout != "DeepDOC" 
        or doc["parser_config"].get("toc_extraction", False)):
        page_size = 10 ** 9  # 等同于整个文档
```

**关键设计意图**：

| parser_id | page_size | 设计原因 |
|-----------|-----------|---------|
| `"paper"` | **22** | 论文通常 10-30 页，22 页能覆盖大多数论文全文，保持章节连贯性 |
| `"one"` | **10^9**（∞） | 整文档一块，必须一次性读取全文才能保持语义完整性 |
| `"knowledge_graph"` | **10^9**（∞） | 知识图谱构建需要全文上下文来抽取实体和关系 |
| `"table"` | **3000 行** | Excel 表格按行数分片，不按页数 |
| 默认（naive 等） | **12** | 平衡并行效率与上下文窗口大小 |

#### Step 2：按 page_size 拆分任务数组

```python
# PDF 文档按页范围拆分
parse_task_array = []
for start_page in range(0, pages, page_size):
    end_page = min(start_page + page_size, pages)
    new_task = {
        "task_id": str(uuid1()),
        "doc_id": doc_id,
        "from_page": start_page,
        "to_page": end_page,
        "task_type": "",        # 标准解析任务
        "parser_id": doc["parser_id"],
        "parser_config": doc["parser_config"],
        "progress": 0.0,
        # ... 其他字段
    }
    parse_task_array.append(new_task)
```

**四种 parser_id 的任务拆分示例**（假设一个 50 页的 PDF）：

```
parser_id = "paper" (page_size=22):
  Task 0: pages [0, 22)   → 22 页
  Task 1: pages [22, 44)  → 22 页
  Task 2: pages [44, 50)  → 6 页
  共 3 个任务

parser_id = "naive" (page_size=12):
  Task 0: pages [0, 12)   → 12 页
  Task 1: pages [12, 24)  → 12 页
  Task 2: pages [24, 36)  → 12 页
  Task 3: pages [36, 48)  → 12 页
  Task 4: pages [48, 50)  → 2 页
  共 5 个任务

parser_id = "one" (page_size=10^9):
  Task 0: pages [0, 50)   → 整个文档
  共 1 个任务

parser_id = "knowledge_graph" (page_size=10^9):
  Task 0: pages [0, 50)   → 整个文档
  共 1 个任务
```

#### Step 3：计算任务摘要（digest）用于去重复用

```python
# 每个任务生成唯一摘要，包含：分块配置 + 页范围
# 如果之前有相同摘要的任务已完成，可直接复用其 chunks
for task in parse_task_array:
    task["digest"] = hashlib.md5(
        json.dumps({
            "parser_id": task["parser_id"],
            "parser_config": task["parser_config"],
            "from_page": task["from_page"],
            "to_page": task["to_page"],
        }).encode()
    ).hexdigest()
```

### 2.3 四种 parser_id 的任务分片规则对比

| parser_id | 分片维度 | 分片大小 | 50页PDF任务数 | 设计意图 |
|-----------|---------|---------|-------------|---------|
| **paper** | 按页 | 22 页/任务 | 3 | 保持论文章节连贯，避免摘要/引言被截断 |
| **table** | 按行 | 3000 行/任务 | N/A(PDF不适用) | 表格数据按行数切分，适合 Excel |
| **one** | 不分片 | 整个文档 | 1 | 需要完整全文上下文，如短文档或全文检索 |
| **knowledge_graph** | 不分片 | 整个文档 | 1 | 实体关系抽取需要全局上下文 |
| naive（默认） | 按页 | 12 页/任务 | 5 | 平衡并行效率与上下文窗口 |

---

## 三、Redis Stream 消息队列机制

### 3.1 任务推入队列（生产者）

**文件**：`api/db/services/task_service.py`（第 460-464 行）

```python
# 只推送未完成的任务（progress < 1.0 的新任务或需重试的任务）
unfinished_task_array = [
    task for task in parse_task_array if task["progress"] < 1.0
]

for unfinished_task in unfinished_task_array:
    assert REDIS_CONN.queue_product(
        settings.get_svr_queue_name(priority),  # 队列名
        message=unfinished_task                  # 任务消息体
    ), "Can't access Redis. Please check the Redis' status."
```

**队列命名规则**（`common/settings.py`，第 128-131 行）：

```python
def get_svr_queue_name(priority: int) -> str:
    if priority == 0:
        return SVR_QUEUE_NAME           # "rag_flow_svr_queue"
    return f"{SVR_QUEUE_NAME}_{priority}"  # "rag_flow_svr_queue_1"
```

| 优先级 | 队列名 | 用途 |
|-------|--------|------|
| Priority 0 | `rag_flow_svr_queue` | 默认队列（普通任务） |
| Priority 1 | `rag_flow_svr_queue_1` | 高优先级队列（紧急任务） |

**Redis Stream XADD 操作**（`rag/utils/redis_conn.py`，第 350-361 行）：

```python
def queue_product(self, queue, message) -> bool:
    """将任务推入 Redis Stream"""
    for _ in range(3):  # 失败重试 3 次
        try:
            # 将任务字典 JSON 序列化后包装
            payload = {"message": json.dumps(message)}
            # 使用 Redis XADD 命令追加到 Stream 末尾
            self.REDIS.xadd(queue, payload)
            return True
        except Exception as e:
            logging.exception(f"RedisDB.queue_product {queue} got exception: {e}")
            self.__open__()  # 重新建立 Redis 连接
    return False
```

**推入 Redis Stream 的消息结构**：

```
Stream Key: rag_flow_svr_queue
Message ID: 1718123456789-0
Message Body: {
    "message": "{\"task_id\": \"xxx\", \"doc_id\": \"xxx\", 
                 \"from_page\": 0, \"to_page\": 22,
                 \"parser_id\": \"paper\", 
                 \"parser_config\": {...},
                 \"progress\": 0.0, ...}"
}
```

### 3.2 任务消费（消费者）

**文件**：`rag/svr/task_executor.py`（第 173-234 行）

```python
async def collect():
    """从 Redis Stream 消费任务"""
    svr_queue_names = settings.get_svr_queue_names()
    # 返回 ["rag_flow_svr_queue_1", "rag_flow_svr_queue"]
    # 优先读取高优先级队列
    
    for svr_queue_name in svr_queue_names:
        # 1. 先尝试获取之前未确认的消息（故障恢复）
        redis_msg = REDIS_CONN.queue_consumer(
            svr_queue_name, 
            SVR_CONSUMER_GROUP_NAME,  # "rag_flow_svr_task_broker"
            CONSUMER_NAME,
            msg_id=b"0"  # 读取未确认的消息
        )
        if redis_msg:
            return redis_msg, redis_msg.get_message()
        
        # 2. 再尝试获取新消息
        redis_msg = REDIS_CONN.queue_consumer(
            svr_queue_name,
            SVR_CONSUMER_GROUP_NAME,
            CONSUMER_NAME,
            msg_id=b">"  # 只读新消息
        )
        if redis_msg:
            return redis_msg, redis_msg.get_message()
    
    return None, None
```

**Redis Stream XREADGROUP 操作**（`rag/utils/redis_conn.py`，第 363-408 行）：

```python
def queue_consumer(self, queue_name, group_name, consumer_name, msg_id=b">"):
    """从 Redis Stream 消费任务"""
    for _ in range(3):
        try:
            # 1. 自动创建消费者组（如果不存在）
            group_info = self.REDIS.xinfo_groups(queue_name)
            if not any(gi["name"] == group_name for gi in group_info):
                self.REDIS.xgroup_create(
                    queue_name, group_name, id="0", mkstream=True
                )
            
            # 2. 使用 XREADGROUP 读取消息
            messages = self.REDIS.xreadgroup(
                groupname=group_name,
                consumername=consumer_name,
                count=1,           # 每次读取 1 条
                block=5,           # 阻塞等待 5 秒
                streams={queue_name: msg_id}
            )
            
            # 3. 返回 RedisMsg 包装对象（支持 ack 确认）
            return RedisMsg(messages[0][1][0])
        except Exception as e:
            self.__open__()
    return None
```

**消费顺序**：先读 `rag_flow_svr_queue_1`（高优先级），再读 `rag_flow_svr_queue`（普通优先级）。

### 3.3 消息确认与可靠性保证

```python
# RedisMsg 类封装了消息确认机制
class RedisMsg:
    def ack(self):
        """确认消息已处理完成（XACK）"""
        self.REDIS.xack(queue_name, group_name, msg_id)
    
    def get_message(self):
        """解析消息体"""
        return json.loads(self.msg_data["message"])
```

**可靠性保证机制**：

```
┌──────────────────────────────────────────────────────────┐
│              Redis Stream 可靠性保证                       │
├──────────────────────────────────────────────────────────┤
│                                                          │
│  1. 消费者组（Consumer Group）                            │
│     └── 同一消息只会被组内一个消费者处理                     │
│                                                          │
│  2. 消息确认（XACK）                                      │
│     └── 处理完成后发送 ACK，未确认的消息可被重新消费         │
│                                                          │
│  3. 未确认消息恢复                                        │
│     └── collect() 先用 msg_id="0" 读取未确认消息           │
│     └── 再用 msg_id=">" 读取新消息                         │
│                                                          │
│  4. 生产者重试                                            │
│     └── queue_product() 失败后重试 3 次，自动重连 Redis     │
│                                                          │
│  5. 消费者重试                                            │
│     └── queue_consumer() 失败后重试 3 次，自动重连 Redis    │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

**任务状态流转**：

```
UNSTART("0") → RUNNING("1") → DONE("3") / FAIL("4")
                     ↑
                     └── CANCEL("2")（用户取消）
```

---

## 四、四种 parser_id 的分块策略深度分析

### 4.1 FACTORY 分块器注册表

**文件**：`rag/svr/task_executor.py`（第 83-100 行）

```python
# 分块器工厂：parser_id → 分块器模块
FACTORY = {
    "general": naive,
    ParserType.NAIVE.value: naive,       # "naive"
    ParserType.PAPER.value: paper,       # "paper"    ← 论文分块
    ParserType.BOOK.value: book,         # "book"
    ParserType.PRESENTATION.value: presentation,
    ParserType.MANUAL.value: manual,
    ParserType.LAWS.value: laws,
    ParserType.QA.value: qa,
    ParserType.TABLE.value: table,       # "table"    ← 表格分块
    ParserType.RESUME.value: resume,
    ParserType.PICTURE.value: picture,
    ParserType.ONE.value: one,           # "one"      ← 整文档一块
    ParserType.AUDIO.value: audio,
    ParserType.EMAIL.value: email,
    ParserType.KG.value: naive,          # "knowledge_graph" ← 复用 naive
    ParserType.TAG.value: tag,
}
```

**关键发现**：`knowledge_graph` 的分块阶段直接复用 `naive`（通用分块器），其知识图谱的实体-关系抽取发生在后续的 `do_handle_task()` 中的 GraphRAG 阶段，而非分块阶段。

### 4.2 paper（论文分块）

**文件**：`rag/app/paper.py`（第 144-255 行）

#### 触发条件

```python
# task["parser_id"] == "paper" 时
chunker = FACTORY["paper"]  # → paper 模块
cks = await thread_pool_exec(chunker.chunk, ...)
```

#### 分块流程

```python
def chunk(filename, binary=None, from_page=0, to_page=100,
          lang="English", callback=None, kb_id=None,
          parser_config=None, tenant_id=None):
    """
    paper.chunk() 核心逻辑
    仅支持 PDF 文件，其他格式抛出 NotImplementedError
    """
```

**Step 1：PDF 解析（两种模式）**

```python
# 模式 A：使用 DeepDOC 布局识别器
if parser_config["layout_recognize"] == "DeepDOC":
    pdf = Pdf(filename, binary)
    # 自定义 Pdf 类继承自 PdfParser，返回结构化结果
    sections, tables = pdf(
        callback,
        is_english=True if pdf.lang == "en" else False,
        parser_config=parser_config,
        mode="paper",  # ← paper 模式
    )
    # sections 结构: [{"title": ..., "authors": ..., "abstract": ..., 
    #                   "sections": [...], "tables": [...]}]

# 模式 B：使用其他布局识别器（MinerU、Docling 等）
else:
    parser = PARSERS.get(layout_recognize, by_deepdoc)
    sections, tables = parser(filename, binary, from_page, to_page, 
                               callback, lang, parser_config)
    # 使用 parse_method="paper" 参数
```

**Step 2：提取论文元数据**

```python
# 从前 32 个布局框中识别标题、作者、摘要
for i, (fst, snd) in enumerate(boxes[:32]):
    if fst["type"] == "title" and i < 5:
        title = fst["text"]
    if fst["type"] == "figure caption" and "author" in fst["text"].lower():
        authors = fst["text"]
    if "abstract" in fst["text"].lower() or "摘要" in fst["text"]:
        abstract_text = fst["text"]
```

**Step 3：摘要处理（完整块，不切分）**

```python
# 摘要作为单个完整 chunk，不进行任何切分
cks.append({
    "content_with_weight": "\n".join(abstract_text),
    "content": "\n".join(abstract_text),
    "docnm_kwd": filename,
    "title_tks": rag_tokenizer.tokenize(title),
    "important_kwd": ["abstract", "summary"],  # ← 特殊关键词标记
    "chunks": [],
})
```

**Step 4：章节合并（按标题层级）**

```python
# 使用 bullets_category() 识别标题层级（H1/H2/H3...）
# 使用 title_frequency() 统计标题出现频率确定层级
# 同一层级的段落合并为单个 chunk

# 算法：
# 1. 扫描所有段落，提取标题模式（数字编号、粗体等）
# 2. 根据标题格式统计频率，确定层级
# 3. 将同一 sec_id 的段落合并
# 4. 每个合并后的段落成为一个 chunk
```

**Step 5：表格处理**

```python
# 表格独立分词
for table in tables:
    table_chunks = tokenize_table(table, filename, ...)
    cks.extend(table_chunks)
```

**paper 分块策略总结**：

```
输入: PDF 文件
    │
    ├── DeepDOC 模式
    │     ├── OCR → 布局分析 → 表格识别
    │     ├── 提取: title / authors / abstract
    │     ├── 摘要 → 完整 chunk（不切分）
    │     ├── 章节 → 按标题层级合并
    │     └── 表格 → 独立分词
    │
    └── 其他布局模式
          └── 使用 naive 的 PARSERS，parse_method="paper"
              └── 同样提取标题/摘要，按论文结构合并

输出: chunks 列表
    每个 chunk = {
        "content_with_weight": "合并后的文本",
        "content": "纯文本",
        "docnm_kwd": "文件名",
        "important_kwd": ["abstract"] 或 [],
        ...
    }
```

### 4.3 table（表格分块）

**文件**：`rag/app/table.py`（第 361-506 行）

#### 触发条件

```python
# task["parser_id"] == "table" 时
# 注意：此分块器主要处理 Excel/CSV 文件，PDF 文件一般不使用
chunker = FACTORY["table"]  # → table 模块
```

#### 分块流程

**Step 1：文件解析**

```python
def chunk(filename, binary=None, from_page=0, to_page=12,
          lang="English", callback=None, kb_id=None,
          parser_config=None, tenant_id=None):
    """
    table.chunk() 核心逻辑
    支持: xlsx, xls, csv, txt (tab-delimited)
    """
    
    # 使用 Excel() 解析器（继承自 ExcelParser）
    excel = Excel(filename, binary)
    
    # 处理合并单元格、多级表头
    # 提取 Excel 中嵌入的图片
    excel.crop(0, 100000, binary)
```

**Step 2：列类型推断**

```python
# 自动识别每列的数据类型
# column_data_type() 函数分析列值：
#   - text: 文本列 → _tks (分词) / _long (长文本)
#   - int: 整数列 → _flt (浮点)
#   - float: 浮点列 → _flt
#   - datetime: 日期列 → _dt
#   - bool: 布尔列 → _kwd
#   - keyword: 关键词列 → _kwd
```

**Step 3：每行生成一个 chunk**

```python
# 每一行数据成为一个独立的 chunk
for row_idx, row in enumerate(df):
    # 构建 field:value 键值对格式
    chunk_content = ""
    for col_name, value in row.items():
        db_field = field_map[col_name]  # 列名 → 拼音化 DB 字段名
        chunk_content += f"- {col_name}: {value}\n"
    
    cks.append({
        "content_with_weight": chunk_content,
        "content": chunk_content,
        "docnm_kwd": filename,
        # 根据列类型存储到对应字段
        f"{db_field}_tks": rag_tokenizer.tokenize(value),  # 文本
        f"{db_field}_flt": float(value),                     # 数值
        f"{db_field}_kwd": value,                             # 关键词
        f"{db_field}_dt": value,                              # 日期
    })
```

**Step 4：字段映射写回知识库**

```python
# 将列名到 DB 字段的映射写入知识库配置
# 供后续检索时使用
kb.parser_config["field_map"] = field_map
KnowledgebaseService.update_parser_config(kb_id, kb.parser_config)
```

**table 分块策略总结**：

```
输入: Excel/CSV 文件
    │
    ├── 解析: ExcelParser (openpyxl/pandas)
    │     ├── 处理合并单元格
    │     ├── 处理多级表头
    │     └── 提取嵌入图片
    │
    ├── 列类型推断
    │     ├── text → _tks / _long
    │     ├── int/float → _flt
    │     ├── datetime → _dt
    │     └── keyword → _kwd
    │
    └── 每行 → 1 个 chunk
          格式: "- 列名: 值\n- 列名: 值\n..."

输出: chunks 列表（每行一个 chunk + 类型化字段）
```

### 4.4 one（整文档一块）

**文件**：`rag/app/one.py`（第 58-166 行）

#### 触发条件

```python
# task["parser_id"] == "one" 时
# 整个文档（无论多少页）只生成 1 个 chunk
chunker = FACTORY["one"]  # → one 模块
```

#### 分块流程

```python
def chunk(filename, binary=None, from_page=0, to_page=10000,
          lang="English", callback=None, kb_id=None,
          parser_config=None, tenant_id=None):
    """
    one.chunk() 核心逻辑
    一个文件 = 一个 chunk，保持原始文本顺序
    支持: docx, pdf, xlsx, txt/md/mhtml/mhx, html, doc
    """
```

**根据文件类型选择解析器**：

```python
# PDF 文件
if filename.lower().endswith(".pdf"):
    # 使用 naive 模块的 PARSERS（根据 layout_recognize 设置）
    parser = PARSERS.get(parser_config.get("layout_recognize", "DeepDOC"), by_deepdoc)
    sections, tables = parser(filename, binary, from_page, to_page,
                               callback, lang, parser_config)
    # 将所有 sections 合并为单个文本
    txt = "\n".join([sec[0] for sec in sections])

# DOCX 文件
elif filename.lower().endswith(".docx"):
    # 使用 naive.Docx() 解析器
    docx_parser = naive.Docx(filename, binary)
    sections, images = docx_parser(callback, toc=True)
    txt = "\n".join([sec[0] for sec in sections])

# Excel 文件
elif filename.lower().endswith((".xlsx", ".xls")):
    # 使用 ExcelParser 的 HTML 输出模式
    txt = ExcelParser().html(filename, binary)

# TXT/MD 文件
else:
    # 直接读取文本，按换行分隔
    txt = binary.decode()
```

**生成单个 chunk**：

```python
# 所有文本合并为一个 chunk
cks = [{
    "content_with_weight": txt,
    "content": txt,
    "docnm_kwd": filename,
    "title_tks": rag_tokenizer.tokenize(filename),
    "content_with_weight_tks": rag_tokenizer.tokenize(txt),
    # ... 其他字段
}]
```

**one 分块策略总结**：

```
输入: 任意支持的文件
    │
    ├── PDF → 通过 PARSERS 解析所有页
    ├── DOCX → 通过 naive.Docx() 解析
    ├── Excel → 通过 ExcelParser().html()
    ├── TXT/MD → 直接读取
    └── HTML → HtmlParser()
    
    └── 所有内容合并 → 1 个 chunk

输出: 1 个 chunk（包含完整文档文本）
    特点: 适合短文档或需要全文上下文的场景
    限制: 文本过长时可能超出 embedding 模型的最大长度
```

### 4.5 knowledge_graph（知识图谱分块）

**文件**：`rag/app/naive.py`（第 736-1067 行）

#### 触发条件

```python
# task["parser_id"] == "knowledge_graph" 时
# 注意: FACTORY 中 KG 映射到 naive 模块
chunker = FACTORY["knowledge_graph"]  # → naive 模块
```

**关键设计**：知识图谱在分块阶段使用 `naive`（通用分块器），**实体关系抽取在后续阶段处理**。

#### 分块流程（与 naive 相同）

```python
# naive.chunk() 对 PDF 文件的处理
if filename.lower().endswith(".pdf"):
    # 根据 layout_recognize 选择解析器
    parser = PARSERS.get(layout_recognize, by_deepdoc)
    sections, tables = parser(filename, binary, from_page, to_page,
                               callback, lang, parser_config)
    
    # 使用 naive_merge() 合并文本片段
    # 按 delimiter 分割，然后按 chunk_token_num 合并
    txts = naive_merge(sections, parser_config["chunk_token_num"],
                       delimiter=parser_config["delimiter"])
    
    # 每个合并后的文本段成为一个 chunk
    for i, (txt, _) in enumerate(txts):
        cks.append({
            "content_with_weight": txt,
            "content": txt,
            "docnm_kwd": filename,
            # ...
        })
```

#### 知识图谱的真正处理阶段

```python
# rag/svr/task_executor.py (lines 1053-1100)
# 在 do_handle_task() 中，当 task_type == "graphrag" 时：

if task["task_type"] == "graphrag":
    # 自动初始化 GraphRAG 配置
    graphrag_config = task["parser_config"].get("graphrag", {})
    if not graphrag_config:
        graphrag_config = {
            "entity_types": ["organization", "person", "geo", 
                           "event", "category"],
            "method": "light",
        }
    
    # 绑定 Chat LLM 模型
    llm_bnd = LLMBundle(tenant_id, LLMType.CHAT, llm_id=task["llm_id"])
    
    # 执行 GraphRAG 实体关系抽取
    await run_graphrag_for_kb(
        kb_id=task["kb_id"],
        doc_id=task["doc_id"],
        llm_bnd=llm_bnd,
        graphrag_config=graphrag_config,
        callback=progress_callback,
    )
```

**knowledge_graph 完整流程**：

```
输入: PDF 文件
    │
    ├── Phase 1: 分块（使用 naive 分块器）
    │     ├── PDF → DeepDOC/MinerU 解析
    │     ├── naive_merge() 合并文本
    │     └── 生成基础 chunks
    │
    ├── Phase 2: 向量化（embedding）
    │     └── chunks → embedding 模型 → 向量
    │
    ├── Phase 3: 索引写入（insert_chunks）
    │     └── chunks + 向量 → Elasticsearch/Infinity
    │
    └── Phase 4: 知识图谱构建（GraphRAG）
          ├── 从 chunks 中抽取实体（organization, person...）
          ├── 抽取实体关系
          ├── 实体消歧（resolution）
          ├── 社区检测（community）
          └── 存储知识图谱到 graphrag_graph 字段

输出: chunks + 知识图谱（实体-关系网络）
```

---

## 五、build_chunks() 统一分块执行流程

**文件**：`rag/svr/task_executor.py`（第 242-514 行）

无论 `parser_id` 是 paper、table、one 还是 knowledge_graph，都通过 `build_chunks()` 统一执行：

```python
@timeout(60 * 80, 1)  # 80 分钟超时
async def build_chunks(task, progress_callback):
    """统一分块执行入口"""
    
    # Step 1: 文件大小检查
    if binary.size > settings.DOC_MAXIMUM_SIZE:
        raise Exception(f"File too large")
    
    # Step 2: 选择分块器（核心路由）
    chunker = FACTORY[task["parser_id"].lower()]
    #  paper → paper 模块
    #  table → table 模块
    #  one → one 模块
    #  knowledge_graph → naive 模块
    
    # Step 3: 从 MinIO 获取文件二进制
    binary = settings.STORAGE_IMPL.get(
        addr["storage_id"], addr["storage_path"]
    )
    
    # Step 4: 在线程池中执行分块（受信号量控制，并发=1）
    cks = await thread_pool_exec(
        chunker.chunk,
        task["name"],
        binary=binary,
        from_page=task["from_page"],    # ← page_size 决定的起始页
        to_page=task["to_page"],        # ← page_size 决定的结束页
        lang=task["language"],
        callback=progress_callback,
        kb_id=task["kb_id"],
        parser_config=task["parser_config"],
        tenant_id=task["tenant_id"],
    )
    
    # Step 5: 分块后处理
    for ck in cks:
        # 5a. 生成唯一块 ID（xxhash）
        ck["id"] = xxhash.xxh64(
            ck["content_with_weight"] + task["doc_id"]
        ).hexdigest()
        
        # 5b. 设置创建时间
        ck["create_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 5c. 图片上传到 MinIO
        if "image" in ck:
            ck["img_id"] = await image2id(ck["image"], task["doc_id"], ...)
    
    # Step 6: 可选的 LLM 增强（并行执行）
    await asyncio.gather(
        auto_keywords(task, cks),      # 自动关键词提取
        auto_questions(task, cks),     # 自动问题生成
        enable_metadata(task, cks),    # 元数据提取
        tag_kb_ids(task, cks),         # 内容标签
    )
    
    return cks
```

**四种 parser_id 的 chunker.chunk() 调用差异**：

| parser_id | chunker.chunk() 的关键差异 |
|-----------|--------------------------|
| `paper` | 返回结构化论文内容（标题/作者/摘要/章节），摘要不切分 |
| `table` | 返回 field:value 键值对，每行一个 chunk，带类型化字段 |
| `one` | 返回单个 chunk，包含完整文档文本 |
| `knowledge_graph`（naive） | 返回按 delimiter + token 数切分的 chunks |

---

## 六、do_handle_task() 完整处理管线

**文件**：`rag/svr/task_executor.py`（第 949-1189 行）

```python
@timeout(60 * 60 * 3, 1)  # 3 小时超时
async def do_handle_task(task):
    """任务处理主函数"""
    
    # ─────────── 任务类型路由 ───────────
    
    if task["task_type"] == "memory":
        return await handle_save_to_memory_task(...)
    
    if task["task_type"] == "dataflow":
        return await run_dataflow(...)
    
    if task["task_type"] == "raptor":
        return await run_raptor_for_kb(...)
    
    if task["task_type"] == "graphrag":
        return await run_graphrag_for_kb(...)
    
    # ─────────── 标准解析流程（paper/table/one/KG通用） ───────────
    
    # Step 1: 初始化 Embedding 模型
    llm_bnd = LLMBundle(tenant_id, LLMType.EMBEDDING, llm_id=embd_id)
    vector_size = llm_bnd.encode(["ok"])[0].shape[-1]
    
    # Step 2: 初始化知识库索引
    init_kb()  # 在 ES/Infinity 中创建索引
    
    # Step 3: 分块
    chunks = await build_chunks(task, progress_callback)
    #  ← 这里调用 FACTORY[parser_id].chunk()
    #  paper: 论文结构化分块
    #  table: 表格行级分块
    #  one: 整文档一块
    #  KG(naive): 通用分块
    
    # Step 4: 向量化
    chunks = await embedding(llm_bnd, chunks, task, progress_callback)
    # 标题向量 × 0.1 + 内容向量 × 0.9
    
    # Step 5: 写入索引
    await insert_chunks(chunks, task, progress_callback)
    # 批量写入 Elasticsearch/Infinity
    
    # Step 6: 更新文档统计
    DocumentService.increment_chunk_num(doc_id, dataset_id, 
                                         token_count, chunk_count, 0)
```

**四种 parser_id 在 do_handle_task 中的完整路径**：

```
paper → build_chunks → paper.chunk() → embedding → insert_chunks
                                                    ↓
                                              Task DONE ✓

table → build_chunks → table.chunk() → embedding → insert_chunks
                                                    ↓
                                              Task DONE ✓

one → build_chunks → one.chunk() → embedding → insert_chunks
                                                ↓
                                          Task DONE ✓

KG → build_chunks → naive.chunk() → embedding → insert_chunks
                                                  ↓
                                            如果 task_type == "graphrag":
                                            run_graphrag_for_kb()
                                            ↓
                                            实体关系抽取 → 知识图谱存储
                                            ↓
                                            Task DONE ✓
```

---

## 七、DeepDoc PDF 解析管线（底层引擎）

**文件**：`deepdoc/parser/pdf_parser.py`（1509 行）

无论使用哪种 `parser_id`，当底层使用 DeepDOC 布局识别器时，都会调用 `RAGFlowPdfParser` 的解析管线：

```python
class RAGFlowPdfParser:
    """RAGFlow 核心 PDF 解析器"""
    
    def __init__(self):
        # 初始化各组件
        self.ocr = OCR()                                    # PaddleOCR
        self.layout_rec = LayoutRecognizer("layout")        # 布局识别（ONNX）
        self.table_structure_rec = TableRecognizer("table_structure")  # 表格结构
        self.updown_concat_model = xgboost.XGBClassifier()  # 文本合并决策
```

**解析管线（7 个阶段）**：

```python
def __call__(self, images, callback, ...):
    """PDF 解析主流程"""
    
    # Stage 1: PDF 渲染为图像
    self.__images__(images, zoomin=3)  # 72 DPI × 3 = 216 DPI
    
    # Stage 2: OCR 文字检测与识别
    self.__ocr()
    # → PaddleOCR 检测文本框 → 批量识别 → 与 pdfplumber 字符合并
    
    # Stage 3: 布局分析
    self._layouts_rec()
    # → ONNX 模型分类: text/table/figure/title/caption/reference
    
    # Stage 4: 表格结构识别
    self._table_transformer_job()
    # → 识别行(R)/表头(H)/列(C)/合并(SP) → 构建 HTML 表格
    
    # Stage 5: 水平文本合并
    self._text_merge()
    # → 同一版面内相邻文本框横向合并
    
    # Stage 6: 垂直文本合并（XGBoost 决策）
    self._concat_downward()
    # → 30+ 维特征 → XGBoost 分类器决定上下文本是否合并
    # → KMeans 聚类检测列布局
    
    # Stage 7: 表格/图表提取
    self._extract_table_figure()
    # → 裁剪图像 → 匹配标题 → 跨页合并
    
    return sections, tables
```

**各 parser_id 对 DeepDoc 管线的调用方式**：

| parser_id | DeepDoc 调用方式 | 特殊处理 |
|-----------|-----------------|---------|
| `paper` | `Pdf(callback, mode="paper")` → 提取标题/作者/摘要 | 论文元数据提取 |
| `table` | 不直接调用（table 主要处理 Excel） | — |
| `one` | `Pdf(callback)` → 返回全部 sections | 合并为单个 chunk |
| `knowledge_graph`（naive） | `Pdf(callback)` → 通过 naive_merge() 切分 | 按 token 数合并 |

---

## 八、完整流程图总结

```
┌──────────────────────────────────────────────────────────────────────────┐
│            四种 parser_id 的 PDF 解析完整流程对比                          │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  用户点击"解析" → document_app.run() → DocumentService.run()             │
│       │                                                                  │
│       ▼                                                                  │
│  queue_tasks()                                                           │
│       │                                                                  │
│       ├── parser_id="paper"     → page_size=22 → N 个任务                │
│       ├── parser_id="table"     → 3000行/任务 (仅Excel)                  │
│       ├── parser_id="one"       → page_size=∞  → 1 个任务                │
│       └── parser_id="KG"        → page_size=∞  → 1 个任务                │
│       │                                                                  │
│       ▼                                                                  │
│  Redis XADD → "rag_flow_svr_queue"                                       │
│       │                                                                  │
│       ▼                                                                  │
│  TaskExecutor: collect() ← XREADGROUP                                    │
│       │                                                                  │
│       ▼                                                                  │
│  do_handle_task()                                                        │
│       │                                                                  │
│       ▼                                                                  │
│  build_chunks() → FACTORY[parser_id].chunk()                             │
│       │                                                                  │
│       ├── paper.chunk()                                                   │
│       │     ├── DeepDOC → 提取 title/authors/abstract                    │
│       │     ├── 摘要 → 完整 chunk                                        │
│       │     ├── 章节 → 按标题层级合并                                     │
│       │     └── 表格 → 独立分词                                          │
│       │                                                                  │
│       ├── table.chunk()                                                   │
│       │     ├── ExcelParser → 列类型推断                                  │
│       │     └── 每行 → 1 个 chunk (field:value)                          │
│       │                                                                  │
│       ├── one.chunk()                                                     │
│       │     ├── PDF → DeepDOC 全页解析                                    │
│       │     └── 所有内容 → 1 个 chunk                                    │
│       │                                                                  │
│       └── naive.chunk() (KG)                                              │
│             ├── PDF → DeepDOC 解析                                       │
│             ├── naive_merge() → 按 token 数切分                          │
│             └── 每段 → 1 个 chunk                                        │
│       │                                                                  │
│       ▼                                                                  │
│  embedding() → 标题向量×0.1 + 内容向量×0.9                               │
│       │                                                                  │
│       ▼                                                                  │
│  insert_chunks() → Elasticsearch / Infinity                              │
│       │                                                                  │
│       ▼ (仅 knowledge_graph)                                             │
│  run_graphrag_for_kb() → 实体抽取 → 关系构建 → 知识图谱存储               │
│       │                                                                  │
│       ▼                                                                  │
│  Task DONE ✓                                                             │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

> **代码文件索引**：
> 
> | 文件路径 | 核心内容 |
> |---------|---------|
> | `api/apps/document_app.py` | 用户触发入口（run/parse） |
> | `api/db/services/task_service.py` | `queue_tasks()` 任务拆分与入队 |
> | `rag/utils/redis_conn.py` | `queue_product()` / `queue_consumer()` Redis Stream 操作 |
> | `common/constants.py` | `ParserType` 枚举、队列常量 |
> | `common/settings.py` | `get_svr_queue_name()` 队列命名 |
> | `rag/svr/task_executor.py` | `FACTORY`、`build_chunks()`、`do_handle_task()`、`collect()` |
> | `rag/app/paper.py` | 论文分块器 `chunk()` |
> | `rag/app/table.py` | 表格分块器 `chunk()` |
> | `rag/app/one.py` | 整文档分块器 `chunk()` |
> | `rag/app/naive.py` | 通用分块器（KG 复用） |
> | `deepdoc/parser/pdf_parser.py` | DeepDoc PDF 解析管线 |
> 
> **文档生成时间**：2026年6月  
> **分析代码版本**：ragflow-main（GitHub infiniflow/ragflow v0.23.1）
