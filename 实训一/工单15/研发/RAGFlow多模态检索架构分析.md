# RAGFlow 多模态检索架构深度分析

> **工单编号：** 人工智能NLP-RAG-优化技术图纸与文本的跨模态检索流程工单  
> **版本：** v0.23.1  
> **分析日期：** 2026年6月9日  
> **分析范围：** RAGFlow 源码检索流程、多模态检索瓶颈识别、优化技术方案设计

---

## 目录

1. [系统架构总览](#1-系统架构总览)
2. [检索流程全链路分析](#2-检索流程全链路分析)
3. [查询理解与重写模块](#3-查询理解与重写模块)
4. [多路召回策略](#4-多路召回策略)
5. [混合排序与融合机制](#5-混合排序与融合机制)
6. [重排（Re-Rank）实现](#6-重排re-rank实现)
7. [多模态检索现状分析](#7-多模态检索现状分析)
8. [识别出的核心瓶颈](#8-识别出的核心瓶颈)
9. [优化技术方案设计](#9-优化技术方案设计)

---

## 1. 系统架构总览

### 1.1 整体架构

RAGFlow 是一个基于深度文档理解的开源 RAG 引擎，采用微服务架构部署。其检索系统涉及以下核心组件：

```
┌─────────────────────────────────────────────────────────────┐
│                      用户提问入口                             │
│              POST /chat/completions (chat_api.py)            │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  对话编排层 (dialog_service.py)               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ 会话管理      │  │ 查询预处理    │  │ Prompt 组装       │   │
│  │ Conversation  │  │ Refinement   │  │ Template Fill    │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  检索引擎层 (search.py → Dealer)              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ 查询构建      │  │ 多路召回      │  │ 重排融合          │   │
│  │ FulltextQuery │  │ Keyword+Vec  │  │ Re-Rank          │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                  存储引擎层 (ES / Infinity / OceanBase)       │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │ 全文索引       │  │ 向量索引      │  │ 混合融合          │   │
│  │ BM25/MatchText│  │ KNN/Cosine   │  │ Weighted Sum     │   │
│  └──────────────┘  └──────────────┘  └──────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 核心代码文件定位

| 模块 | 文件路径 | 职责 |
|------|----------|------|
| API 入口 | `api/apps/restful_apis/chat_api.py` | 接收用户提问，触发对话流程 |
| 对话编排 | `api/db/services/dialog_service.py` | 核心编排：查询预处理→检索→Prompt组装→LLM生成 |
| 检索引擎 | `rag/nlp/search.py` | `Dealer` 类：多路召回、融合、重排 |
| 查询构建 | `rag/nlp/query.py` | `FulltextQueryer`：查询分词、权重计算、同义词扩展 |
| 分词器 | `rag/nlp/rag_tokenizer.py` | 中英文分词（C++ 原生实现） |
| 词权重 | `rag/nlp/term_weight.py` | TF-IDF 词权重计算 |
| 同义词 | `rag/nlp/synonym.py` | 同义词扩展（自定义词典 + WordNet） |
| ES 连接 | `rag/utils/es_conn.py` | Elasticsearch 查询构建与执行 |
| 知识库服务 | `api/apps/services/dataset_api_service.py` | 知识库级检索参数配置 |
| 文档解析 | `rag/svr/task_executor.py` | 文档解析、分块、向量化 |

### 1.3 关键配置参数

| 参数 | 默认值 | 所在位置 | 说明 |
|------|--------|----------|------|
| `similarity_threshold` | 0.2 | 助手设置 | 相似度阈值，低于此值的结果被过滤 |
| `vector_similarity_weight` | 0.3 | 助手设置 | 向量相似度权重（1-此值为关键词权重） |
| `top_n` | 8 | 助手设置 | 返回的参考片段数量 |
| `top_k` | 1024 | 助手设置 | 检索候选池大小 |
| `rerank_id` | 空 | 助手设置 | 外部重排模型 ID |
| `chunk_token_num` | 512 | 知识库设置 | 每个分块的 token 数 |
| `overlapped_percent` | 0.15 | 知识库设置 | 分块重叠比例 |

---

## 2. 检索流程全链路分析

### 2.1 完整调用链

```
用户提问 "在文件中第11页图3中，编号13的部件相对于编号12的部件的位置关系是？"
    │
    ▼
[1] chat_api.py :: session_completion()
    ├── 解析请求体，提取 messages、chat_id、session_id
    ├── 加载 Dialog 配置（包含 kb_ids、检索参数等）
    └── 创建或加载 Conversation 会话
    │
    ▼
[2] dialog_service.py :: async_chat()
    ├── 判断是否有关联知识库（kb_ids 非空）
    ├── 加载模型（embedding、chat、rerank、TTS）
    ├── 查询预处理：
    │   ├── full_question() — 多轮对话合并
    │   ├── cross_languages() — 跨语言翻译
    │   ├── apply_meta_data_filter() — 元数据过滤
    │   └── 关键词提取（可选）
    └── 调用 retriever.retrieval()
    │
    ▼
[3] search.py :: Dealer.retrieval()
    ├── 构建检索请求（kb_ids、doc_ids、question、参数）
    ├── 调用 self.search() 执行多路召回
    │   ├── qryr.question() — 查询分词与扩展
    │   ├── MatchTextExpr — 全文关键词检索
    │   ├── MatchDenseExpr — 向量语义检索
    │   └── FusionExpr — 加权融合（5%/95%）
    ├── 重排（Re-Rank）
    │   ├── rerank_with_knn() — ES 路径
    │   ├── rerank_by_model() — 外部重排模型
    │   └── rerank() — OceanBase 路径
    ├── 相似度阈值过滤
    └── 返回排序后的候选片段
    │
    ▼
[4] dialog_service.py :: Prompt 组装
    ├── 将检索到的 chunks 格式化为 {knowledge}
    ├── 插入系统提示词模板
    ├── 截断至 max_tokens
    └── 发送给 LLM 生成回答
    │
    ▼
[5] LLM 生成回答
    ├── 流式输出（SSE）
    ├── 引用插入（insert_citations）
    └── 返回给用户
```

### 2.2 各阶段耗时分析

| 阶段 | 典型耗时 | 说明 |
|------|----------|------|
| 查询预处理 | 50-200ms | 分词、同义词扩展、关键词提取 |
| 向量编码 | 10-50ms | Embedding 模型推理 |
| ES 混合检索 | 50-300ms | BM25 + KNN + 融合 |
| 重排 | 100-500ms | 取决于是否使用外部重排模型 |
| LLM 生成 | 1-5s | 取决于模型和输出长度 |

---

## 3. 查询理解与重写模块

### 3.1 查询预处理流水线

`FulltextQueryer.question(txt)` 是查询处理的入口，位于 `rag/nlp/query.py`。

```
原始查询: "在文件中第11页图3中，编号13的部件相对于编号12的部件的位置关系是？"
    │
    ▼
[Step 1] 文本清洗
    ├── add_space_between_eng_zh() — 中英文边界插入空格
    ├── 正则清洗 — 移除特殊字符
    ├── tradi2simp() — 繁体转简体
    ├── strQ2B() — 全角转半角
    └── rmWWW() — 移除停用词（"请问"、"什么"、"怎么"、"the"、"is"等）
    │
    ▼
清洗后: "文件 第11页 图3 编号13 部件 编号12 部件 位置关系"
    │
    ▼
[Step 2] 语言检测
    ├── is_chinese() — 判断 ≥70% token 为非 ASCII
    └── 走中文处理路径
    │
    ▼
[Step 3] 中文分词与权重计算
    ├── rag_tokenizer.tokenize() — 中文分词
    ├── term_weight.Dealer.weights() — TF-IDF 权重
    │   ├── 公式: w = (0.3 × corpus_idf + 0.7 × doc_idf) × ner_weight × pos_weight
    │   ├── NER 类型加权: 机构/地名/股票 → 3x，代词/冠词 → 0.3x
    │   └── 词性加权: 名词/动词 → 高权重，助词 → 低权重
    ├── synonym.Dealer.lookup() — 同义词扩展（自定义词典 + WordNet，最多8个）
    └── rag_tokenizer.fine_grained_tokenize() — 细粒度分词（≥3字符的复合词）
    │
    ▼
[Step 4] 查询构建
    ├── 构建 OR 表达式: 各 token 及其同义词、子词用 OR 连接
    ├── Bigram 生成: 相邻 token 对作为短语查询，权重 ×2
    ├── 近似查询: 多段分词的 token 用 "~2" 近似匹配
    └── 最终输出: Lucene/Infinity 查询 DSL 字符串
```

### 3.2 查询构建示例

对于查询 "编号13的部件"，分词后的 token 可能为 `["编号", "13", "部件"]`，构建的查询表达式类似：

```json
{
  "bool": {
    "should": [
      {"match": {"content_ltks": {"query": "编号 13 部件", "boost": 1.0}}},
      {"match": {"content_ltks": {"query": "编号 13", "boost": 2.0, "type": "phrase"}}},
      {"match": {"content_ltks": {"query": "13 部件", "boost": 2.0, "type": "phrase"}}},
      {"match": {"content_ltks": {"query": "编号~2", "boost": 0.5}}},
      {"match": {"content_ltks": {"query": "部件~2", "boost": 0.5}}}
    ]
  }
}
```

### 3.3 搜索字段与权重

全文检索在以下字段上执行，各有不同的 boost 权重：

| 字段名 | Boost 权重 | 说明 |
|--------|-----------|------|
| `important_kwd` | 30x | 重要关键词（精确匹配） |
| `important_tks` | 20x | 重要关键词（分词匹配） |
| `question_tks` | 20x | 自动生成的问题文本 |
| `title_tks` | 10x | 标题分词 |
| `title_sm_tks` | 5x | 标题小写分词 |
| `content_ltks` | 2x | 正文分词（主要检索字段） |
| `content_sm_ltks` | 1x | 正文小写分词 |

> **关键发现**：`important_kwd` 和 `question_tks` 的 boost 权重最高（30x/20x），这意味着如果文档在解析时生成了高质量的关键词和自动问题，检索效果会显著提升。

---

## 4. 多路召回策略

### 4.1 双路召回架构

RAGFlow 默认采用 **关键词 + 向量** 双路召回策略：

```
                    用户查询
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
   ┌──────────────┐         ┌──────────────┐
   │  关键词检索    │         │  向量检索      │
   │ MatchTextExpr │         │ MatchDenseExpr│
   │ (BM25 全文)   │         │ (Cosine KNN)  │
   └──────┬───────┘         └──────┬───────┘
          │                         │
          └────────────┬────────────┘
                       ▼
              ┌────────────────┐
              │  加权融合       │
              │ FusionExpr     │
              │ "weighted_sum" │
              │ 权重: 5%/95%   │
              └────────┬───────┘
                       ▼
                  候选结果集
```

### 4.2 关键词检索（MatchTextExpr）

位于 `search.py` 的 `Dealer.search()` 方法：

```python
# search.py 第 156-170 行
matchText = MatchTextExpr(
    fields=["title_tks^10", "title_sm_tks^5", "important_kwd^30",
            "important_tks^20", "question_tks^20",
            "content_ltks^2", "content_sm_ltks"],
    matching=query_string,
    minimum_should_match=min_match,  # 默认 0.3
    original_query=original_query
)
```

- 使用 `FulltextQueryer.question()` 生成的扩展查询字符串
- `minimum_should_match=0.3` 表示至少 30% 的查询 token 需要匹配
- ES 端执行 BM25 评分

### 4.3 向量检索（MatchDenseExpr）

```python
# search.py 第 53-68 行
async def get_vector(self, question, emb_mdl, topk, similarity_threshold):
    embedding = await emb_mdl.encode_queries(question)
    return MatchDenseExpr(
        vector_column_name=f"q_{len(embedding[0])}_vec",  # 如 q_1024_vec
        topn=topk,
        embedding=embedding[0],
        distance="cosine",
        extra_options={"similarity": similarity_threshold}
    )
```

- 调用 Embedding 模型（如 bge-m3）将查询编码为向量
- 使用余弦相似度在向量索引中搜索
- `similarity_threshold` 作为最小相似度门槛

### 4.4 引擎级融合（FusionExpr）

```python
# search.py 第 192 行
fusionExpr = FusionExpr(
    "weighted_sum",
    topk,
    {"weights": "0.05,0.95"}  # 硬编码：5% 关键词 / 95% 向量
)
```

> **关键发现**：引擎级融合的权重是**硬编码**的（5%/95%），向量检索占绝对主导。用户配置的 `vector_similarity_weight`（默认 0.3）仅在**第二阶段重排**时生效，不影响初始召回。

### 4.5 降级策略

当首次检索返回 0 结果时，系统自动降级重试：

```python
# search.py 第 200-212 行
if not hit:
    if doc_id:  # 有文档过滤 → 去掉文本/向量约束，仅用过滤
        ...
    else:       # 无文档过滤 → 降低门槛重试
        min_match = 0.1          # 从 0.3 降至 0.1
        similarity_threshold = 0.17  # 从用户阈值降至 0.17
```

---

## 5. 混合排序与融合机制

### 5.1 两阶段融合架构

RAGFlow 采用**两阶段融合**策略：

```
第一阶段：引擎级融合（ES/Infinity 内部）
    ├── BM25 全文得分 × 0.05 + 向量余弦得分 × 0.95
    └── 输出：初步排序的候选列表（top_k 个）

第二阶段：应用级重排（search.py）
    ├── 关键词相似度（token_similarity）
    ├── 向量相似度（KNN 二次调用 / 外部重排模型）
    ├── 排名特征（Tag 相似度 + PageRank）
    └── 最终得分 = term_weight × tksim + vec_weight × vtsim + rank_feature
```

### 5.2 相似度阈值的使用

`similarity_threshold` 在两个阶段都发挥作用：

1. **第一阶段**：作为 ES KNN 搜索的最小相似度门槛
2. **第二阶段**：重排后过滤低于阈值的结果

```python
# search.py 第 679 行
post_threshold = similarity_threshold if vector_similarity_weight > 0 else 0.0
valid_idx = [int(i) for i in sorted_idx if sim_np[i] >= post_threshold]
```

### 5.3 vector_similarity_weight 的双重作用

| 阶段 | 权重来源 | 实际效果 |
|------|----------|----------|
| 第一阶段（ES 融合） | 硬编码 0.95 | 向量占 95%，几乎忽略关键词 |
| 第二阶段（重排） | 用户配置（默认 0.3） | 关键词占 70%，向量占 30% |

> **关键发现**：用户调整 `vector_similarity_weight` 时，实际上只改变第二阶段重排的权重，对第一阶段召回没有影响。这意味着即使用户将权重设为 0.7，初始召回仍然是 95% 向量主导。

---

## 6. 重排（Re-Rank）实现

### 6.1 三种重排路径

根据存储引擎后端和配置，系统选择不同的重排策略：

#### 路径 A：ES + KNN 重排（默认路径）

```python
# search.py :: rerank_with_knn()
def rerank_with_knn(self, ...):
    # 1. 第二次 KNN 调用 — 获取纯余弦相似度
    knn_scores = self._knn_scores(query_vector, candidate_ids)
    
    # 2. 本地计算关键词相似度
    tksim = token_similarity(query_tokens, candidate_tokens)
    
    # 3. 加权融合
    final_score = tkweight * tksim + vtweight * knn_scores + rank_feature
```

`_knn_scores()` 的实现（`search.py` 第 367 行）：
- 对候选 chunk ID 列表发起第二次 KNN 搜索
- 获取每个候选与查询向量的纯余弦相似度
- 避免了将 chunk 向量从 ES 传输到应用层

#### 路径 B：外部重排模型

```python
# search.py :: rerank_by_model()
def rerank_by_model(self, query, chunks, rerank_mdl, ...):
    # 候选上限 64 个
    candidates = chunks[:64]
    
    # 调用外部重排模型（如 BGE-reranker、Cohere）
    vtsim = rerank_mdl.similarity(query, [c["content_with_weight"] for c in candidates])
    
    # 本地关键词相似度
    tksim = token_similarity(query_tokens, candidate_tokens)
    
    # 加权融合
    final_score = tkweight * tksim + vtweight * vtsim + rank_feature
```

#### 路径 C：OceanBase 本地重排

```python
# search.py :: rerank()
def rerank(self, ...):
    # 从 ES 获取 chunk 向量
    chunk_vectors = [c["q_1024_vec"] for c in candidates]
    
    # 本地计算余弦相似度（sklearn）
    cos_sim = cosine_similarity(query_vector, chunk_vectors)
    
    # 本地关键词相似度
    tksim = token_similarity(query_tokens, candidate_tokens)
    
    # 加权融合
    final_score = tkweight * tksim + vtweight * cos_sim + rank_feature
```

### 6.2 关键词相似度算法

`token_similarity()` 位于 `query.py` 第 193 行：

```python
def token_similarity(query_tokens, doc_tokens):
    # 1. 构建查询 token 权重字典（基于 IDF）
    query_weight = {tk: idf_score for tk in query_tokens}
    
    # 2. Bigram 加权：相邻 token 对获得 0.6x 组合权重
    for i in range(len(query_tokens) - 1):
        bigram = query_tokens[i] + query_tokens[i+1]
        query_weight[bigram] = 0.6 * max(query_weight[query_tokens[i]], 
                                          query_weight[query_tokens[i+1]])
    
    # 3. 计算加权重叠度
    overlap = sum(query_weight[k] for k in query_weight if k in doc_tokens)
    total = sum(query_weight.values())
    
    return overlap / total if total > 0 else 0
```

### 6.3 排名特征（Rank Features）

除文本和向量相似度外，还有额外的排名信号：

```python
# search.py 第 334 行
rank_feature_scores = cosine_similarity(query_tag_features, chunk_tag_features) * 10 + pagerank_value
```

- **Tag 特征**：基于文档标签的余弦相似度
- **PageRank**：知识库级别配置的页面权重

---

## 7. 多模态检索现状分析

### 7.1 文档解析与分块流程

```
PDF 文档（如 CN100347506C.pdf）
    │
    ▼
[1] DeepDOC / MinerU 文档解析
    ├── 版面识别（Layout Recognition）
    ├── OCR 文字提取
    ├── 表格识别
    ├── 图片提取
    └── 公式识别
    │
    ▼
[2] 分块（Chunking）
    ├── 按 chunk_token_num 切分（默认 512 token）
    ├── 按 overlapped_percent 设置重叠
    ├── 图片与文本分别处理
    └── 生成 image_table_context_window（图片上下文窗口）
    │
    ▼
[3] 图片描述生成
    ├── 调用 Vision LLM（如 qwen-vl-plus）生成图片描述
    ├── 描述格式：Visual Type / Title / Labels / Data Points / Summary
    └── 语言由 mineru_lang 参数控制（English/Chinese）
    │
    ▼
[4] 向量化
    ├── Embedding 模型（如 bge-m3）编码文本
    ├── 存储到 ES 向量索引（q_1024_vec 字段）
    └── 同时存储原始文本（content_with_weight）和分词文本（content_ltks）
```

### 7.2 图片检索的当前实现

RAGFlow 对图片的处理方式是 **"图片→文本描述→文本检索"**：

```
用户查询: "编号13的部件相对于编号12的部件的位置关系"
    │
    ▼
查询编码为向量 → 在 ES 中搜索最相似的 chunks
    │
    ▼
返回的 chunk 可能是：
    ✗ "Fig. 7: ..."（不相关的图）
    ✗ "The image is a technical schematic..."（英文描述，语义偏移）
    ✓ "图3表示了一种分散装置……紧固机构11在保护管12里设置了链条13"（正确文本）
```

### 7.3 当前多模态检索的数据流

```
                 CN100347506C.pdf
                       │
          ┌────────────┼────────────┐
          ▼            ▼            ▼
     文本块(chunk)  图片块(chunk)  表格块(chunk)
     "部分散料在..."  "Fig.7: The  "表1: ..."
                     diagram..."
          │            │            │
          ▼            ▼            ▼
    bge-m3 编码    bge-m3 编码    bge-m3 编码
    (纯文本向量)   (描述文本向量)  (表格文本向量)
          │            │            │
          └────────────┼────────────┘
                       ▼
              ES 向量索引（q_1024_vec）
                       │
                       ▼
              统一检索（不区分文本/图片）
```

> **关键发现**：当前系统将图片的文本描述和原始文本放在同一个向量空间中检索，**没有独立的图像特征向量**。图片检索完全依赖于文本描述的质量。

---

## 8. 识别出的核心瓶颈

### 瓶颈 1：分块过小导致上下文割裂

**现象**：`chunk_token_num=64` 将描述图3的完整文本切成了多个碎片。

**影响**：
- "部件10是落料架、部件11是紧固机构、部件12是保护管、部件13是链条、部件14是输入管" 这段关键信息被分散在不同 chunk 中
- LLM 无法从单个 chunk 中获得完整的部件关系信息
- 向量检索可能只匹配到部分片段，丢失完整上下文

**代码位置**：`rag/svr/task_executor.py` → 分块逻辑

### 瓶颈 2：图像描述语言不匹配

**现象**：`mineru_lang=English` 导致中文专利文档的图片描述全部用英文生成。

**影响**：
- 中文查询 "调整链条的位置" 需要匹配英文描述 "adjust the position of the chain"
- 向量空间中的语义距离增大
- 关键词检索（content_ltks 使用中文分词）无法匹配英文描述

**代码位置**：`rag/svr/task_executor.py` → 图片描述生成

### 瓶颈 3：查询理解缺乏视觉引用识别

**现象**：查询中的 "图3"、"第11页" 等视觉引用未被特殊处理。

**影响**：
- "图3" 在分词后可能被拆分为 "图" + "3"，丧失作为整体引用的语义
- 系统无法主动定位到特定页面或特定图表
- 依赖纯向量相似度匹配，可能匹配到不相关的图

**代码位置**：`rag/nlp/query.py` → 查询构建逻辑

### 瓶颈 4：引擎级融合权重硬编码

**现象**：`FusionExpr` 权重硬编码为 5%/95%（关键词/向量），用户无法调整。

**影响**：
- 用户配置的 `vector_similarity_weight` 仅影响第二阶段重排
- 对于精确匹配问题（如 "编号13"），关键词检索本应更重要，但被压制到 5%
- 用户调参效果受限

**代码位置**：`rag/nlp/search.py` 第 192 行

### 瓶颈 5：无跨模态重排机制

**现象**：重排阶段仅使用文本相似度和向量相似度，没有专门的图文联合排序。

**影响**：
- 即使检索到了包含图3的页面，也无法确保图文对的完整性
- 图片描述块和对应的文本描述块可能被分别检索，无法联合排序
- 缺乏对 "图纸+文字说明" 作为整体的语义理解

**代码位置**：`rag/nlp/search.py` → `rerank_with_knn()` / `rerank_by_model()`

### 瓶颈 6：image_table_context_window 为 0

**现象**：图片和表格的上下文窗口设置为 0，导致图片与其周围的文本描述完全分离。

**影响**：
- 图片块只包含图片描述文本，不包含周围的技术说明
- 文本块不包含图片信息
- 无法实现 "图文联合" 的检索效果

**代码位置**：知识库 `parser_config` 中的 `image_table_context_window` 参数

---

## 9. 优化技术方案设计

### 9.1 方案总览

```
┌─────────────────────────────────────────────────────────────┐
│                    优化方案架构                               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 优化一：查询理解增强                                    │   │
│  │  · 视觉引用检测（"图3"、"第11页"）                      │   │
│  │  · 查询改写（注入图表定位条件）                          │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 优化二：分块策略优化                                    │   │
│  │  · chunk_token_num: 64 → 512                          │   │
│  │  · overlapped_percent: 0.05 → 0.2                     │   │
│  │  · image_table_context_window: 0 → 2                  │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 优化三：图像描述本地化                                  │   │
│  │  · mineru_lang: English → Chinese                     │   │
│  │  · 确保中文查询与中文描述在同一语义空间                  │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 优化四：检索策略调优                                    │   │
│  │  · vector_similarity_weight: 0.3 → 0.5                │   │
│  │  · 启用 gte-rerank 重排模型                             │   │
│  │  · similarity_threshold: 0.2 → 0.1                    │   │
│  └──────────────────────────────────────────────────────┘   │
│                          │                                   │
│                          ▼                                   │
│  ┌──────────────────────────────────────────────────────┐   │
│  │ 优化五：Prompt 工程优化                                 │   │
│  │  · 禁止 LLM 改写原文                                   │   │
│  │  · 引导优先参考图片描述文本块                            │   │
│  └──────────────────────────────────────────────────────┘   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 9.2 优化一：查询理解增强

**目标**：让系统自动识别查询中的视觉引用（"图3"、"第11页图示"），并将其转化为强化的检索条件。

**实现思路**（在 `rag/nlp/query.py` 中扩展）：

```python
# 新增视觉引用检测函数
def detect_visual_references(query: str) -> dict:
    """
    检测查询中的视觉引用
    返回: {"has_visual_ref": True, "figure": "3", "page": "11", "elements": ["13", "12"]}
    """
    import re
    result = {"has_visual_ref": False}
    
    # 检测 "图X" 引用
    fig_match = re.search(r'图\s*(\d+)', query)
    if fig_match:
        result["has_visual_ref"] = True
        result["figure"] = fig_match.group(1)
    
    # 检测 "第X页" 引用
    page_match = re.search(r'第\s*(\d+)\s*页', query)
    if page_match:
        result["has_visual_ref"] = True
        result["page"] = page_match.group(1)
    
    # 检测部件编号引用
    elem_matches = re.findall(r'(?:编号|部件)\s*(\d+)', query)
    if elem_matches:
        result["elements"] = elem_matches
    
    return result

# 在查询构建时注入视觉定位条件
def enhance_query_with_visual_context(query: str, visual_refs: dict) -> str:
    """
    当检测到视觉引用时，在查询中注入图表定位关键词
    """
    if not visual_refs["has_visual_ref"]:
        return query
    
    enhancements = []
    if "figure" in visual_refs:
        enhancements.append(f"图 {visual_refs['figure']}")
    if "page" in visual_refs:
        enhancements.append(f"第{visual_refs['page']}页")
    if "elements" in visual_refs:
        for elem in visual_refs["elements"]:
            enhancements.append(f"编号{elem}")
            enhancements.append(f"部件{elem}")
    
    # 将增强词追加到查询末尾
    return query + " " + " ".join(enhancements)
```

**效果**：
- 查询 "编号13的部件相对于编号12的部件的位置关系" 会被增强为：
  "编号13的部件相对于编号12的部件的位置关系 图3 第11页 编号13 部件13 编号12 部件12"
- 增强后的查询在关键词检索中能更精确地匹配到包含图3描述的 chunk

### 9.3 优化二：分块策略优化

**目标**：确保技术图纸的完整描述不被切碎，图文上下文保持关联。

**参数调整**（通过 RAGFlow Web UI）：

| 参数 | 原值 | 优化值 | 效果 |
|------|------|--------|------|
| `chunk_token_num` | 64 | **512** | 每个 chunk 包含完整的部件关系描述 |
| `overlapped_percent` | 0.05 | **0.2** | 20% 重叠防止关键信息在边界丢失 |
| `image_table_context_window` | 0 | **2** | 图片周围 2 层文本一起进入 chunk |
| `image_context_size` | 0 | **2** | 为图片保留上下文 |
| `table_context_size` | 0 | **2** | 为表格保留上下文 |

**效果对比**：

```
优化前（chunk_token_num=64）：
  Chunk 1: "图3表示了一种分散装置的实施形式，例如在一个熔化气化器里"
  Chunk 2: "用于将 DRI 装入在移动床上的装置。在一个落料架 10 里通过"
  Chunk 3: "合适的紧固机构 11在一个保护管12 里设置了一根或多根链条13。"
  → LLM 只能看到碎片，无法推理完整关系

优化后（chunk_token_num=512）：
  Chunk 1: "图3表示了一种分散装置的实施形式，例如在一个熔化气化器里
            用于将 DRI 装入在移动床上的装置。在一个落料架 10 里通过
            合适的紧固机构 11在一个保护管12 里设置了一根或多根链条13。
            通过输入管 14导入落料架 10 里的散料通过这些链条或接点而
            实现减速和分散。"
  → LLM 能看到完整的部件关系，正确推理出"调整链条位置需要操作部件11"
```

### 9.4 优化三：图像描述本地化

**目标**：将图片描述从英文改为中文，消除跨语言语义鸿沟。

**参数调整**：

| 参数 | 原值 | 优化值 |
|------|------|--------|
| `mineru_lang` | English | **Chinese** |

**效果对比**：

```
优化前（English）：
  "The diagram includes numbered labels (10, 11, 12, 13, 14) 
   pointing to specific components of the structure."
  → 中文查询 "部件13" 与此英文描述的向量距离较远

优化后（Chinese）：
  "该图包含编号标签（10、11、12、13、14），指向结构的特定组件。"
  → 中文查询与中文描述在同一语义空间，向量距离更近
```

### 9.5 优化四：检索策略调优

**目标**：通过参数调整优化检索精度。

**参数调整**：

| 参数 | 原值 | 优化值 | 理由 |
|------|------|--------|------|
| `vector_similarity_weight` | 0.3 | **0.5** | 向量检索对图文语义匹配更有效 |
| `similarity_threshold` | 0.2 | **0.1** | 降低门槛，召回更多候选 |
| `top_n` | 8 | **10** | 返回更多候选供重排筛选 |
| `rerank_id` | 空 | **gte-rerank** | 启用外部重排模型精排 |

**rerank 模型选择**：

系统已配置 `gte-rerank@Tongyi-Qianwen`（通义千问 rerank 模型），可直接启用。该模型作为交叉编码器，能更精准地判断查询与文档的相关性。

### 9.6 优化五：Prompt 工程优化

**目标**：引导 LLM 精确提取原文，避免改写和概括。

**优化后的系统提示词**：

```
你是专利文档精确问答机器人。规则：

1. **必须从参考资料中逐字提取答案，禁止改写、概括、同义替换。**
   - 如果原文写的是"块状散料"，就回答"块状散料"，绝不能写成"块状矿石"。
2. 回答格式：直接输出答案文本（如"部件11"），不要加任何前缀或解释。
3. 如果参考资料中没有明确信息，回答"未找到"。
4. 对于涉及图片部件编号的问题（如"编号13"、"部件12"、"图3"），
   必须优先参考描述图片的文本块和包含部件编号说明的段落。
5. 对于位置关系问题（"位于"、"之内"、"顶部"），
   仔细阅读图纸描述文本。
6. 注意：有些图的文字描述可能在图片所在页的前几页，需要综合查看。

以下是参考资料：
{knowledge}

以上是参考资料。
```

### 9.7 预期效果

| 测试问题 | 优化前 | 优化后预期 |
|----------|--------|-----------|
| Q1: 哪种物料的分配装置？ | "块状矿石" ✗ | "块状散料" ✓ |
| Q2: 分散装置包含哪个组件？ | 部分正确 | "链条" ✓ |
| Q3: 编号13相对于编号12的位置？ | 无法回答 | "位于编号12的部件之内" ✓ |
| Q4: 编号14位于哪个位置？ | 无法回答 | "顶部" ✓ |
| Q5: 散料从部件14进入后经过？ | 无法回答 | "部件13" ✓ |
| Q6: 调整链条位置需要操作？ | 无法回答 | "部件11" ✓ |

---

## 附录：关键代码位置索引

| 功能 | 文件 | 行号范围 |
|------|------|----------|
| API 入口 | `api/apps/restful_apis/chat_api.py` | L1160-1283 |
| 对话编排 | `api/db/services/dialog_service.py` | L541-770 |
| 检索入口 | `rag/nlp/search.py` | `Dealer.retrieval()` L562 |
| 混合搜索 | `rag/nlp/search.py` | `Dealer.search()` L132-212 |
| 查询构建 | `rag/nlp/query.py` | `FulltextQueryer.question()` L42 |
| 词权重计算 | `rag/nlp/term_weight.py` | `Dealer.weights()` |
| 同义词扩展 | `rag/nlp/synonym.py` | `Dealer.lookup()` |
| ES 查询执行 | `rag/utils/es_conn.py` | `ESConnection.search()` |
| ES KNN 重排 | `rag/nlp/search.py` | `rerank_with_knn()` L443 |
| 外部重排 | `rag/nlp/search.py` | `rerank_by_model()` L513 |
| 文档分块 | `rag/svr/task_executor.py` | chunking 逻辑 |
| 图片描述 | `rag/svr/task_executor.py` | image description 生成 |
| Prompt 组装 | `api/db/services/dialog_service.py` | L752-769 |
