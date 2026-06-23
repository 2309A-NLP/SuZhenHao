# RAGFlow Web UI 参数调试指南

> **版本**：RAGFlow v0.23.1  
> **适用场景**：针对低质量工业 PDF 的解析与信息丢失问题调优  
> **文档生成时间**：2026年6月

---

## 目录

- [一、参数调试总览](#一参数调试总览)
- [二、知识库级别参数](#二知识库级别参数)
- [三、分块策略（Chunk Method）详解](#三分块策略chunk-method详解)
- [四、解析配置（parser_config）详解](#四解析配置parser_config详解)
  - [4.1 布局识别方法（layout_recognize）](#41-布局识别方法layout_recognize)
  - [4.2 分块大小（chunk_token_num）](#42-分块大小chunk_token_num)
  - [4.3 分隔符（delimiter）](#43-分隔符delimiter)
  - [4.4 任务页数（task_page_size）](#44-任务页数task_page_size)
  - [4.5 自动关键词与问题生成](#45-自动关键词与问题生成)
  - [4.6 TOC 目录提取](#46-toc-目录提取)
  - [4.7 Excel 转 HTML](#47-excel-转-html)
  - [4.8 图表上下文窗口](#48-图表上下文窗口)
- [五、RAPTOR 层级摘要配置](#五raptor-层级摘要配置)
- [六、GraphRAG 知识图谱配置](#六graphrag-知识图谱配置)
- [七、检索参数调试](#七检索参数调试)
- [八、MinerU 与 PaddleOCR 子参数](#八mineru-与-paddleocr-子参数)
- [九、文档级别参数覆盖](#九文档级别参数覆盖)
- [十、工业 PDF 调优实战方案](#十工业-pdf-调优实战方案)

---

## 一、参数调试总览

RAGFlow 的参数调试分为三个层级：

```
┌─────────────────────────────────────────────────────────────────┐
│                        参数层级结构                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  L1: 知识库级别（Knowledgebase）                          │   │
│  │  创建知识库时设置，影响该库下所有文档                        │   │
│  │  ├── chunk_method (parser_id)     分块策略                │   │
│  │  ├── embedding_model (embd_id)    嵌入模型                │   │
│  │  ├── parser_config                解析配置（核心）          │   │
│  │  ├── similarity_threshold         相似度阈值               │   │
│  │  └── vector_similarity_weight     向量/关键词权重比         │   │
│  └──────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  L2: 文档级别（Document）                                 │   │
│  │  上传文档时可覆盖知识库默认配置                              │   │
│  │  ├── parser_id                    覆盖分块策略              │   │
│  │  ├── parser_config                覆盖解析参数              │   │
│  │  └── pages                        指定解析页范围            │   │
│  └──────────────────────────────────────────────────────────┘   │
│                          │                                      │
│                          ▼                                      │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  L3: 检索级别（Retrieval）                                │   │
│  │  对话/检索时的参数调整                                      │   │
│  │  ├── similarity_threshold         检索相似度阈值            │   │
│  │  ├── vector_similarity_weight     向量 vs 关键词权重        │   │
│  │  ├── top_n                        返回结果数                │   │
│  │  └── rerank_model                 重排序模型                │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 二、知识库级别参数

创建知识库时可配置以下参数：

| 参数 | UI 名称 | 类型 | 默认值 | 说明 |
|------|---------|------|--------|------|
| `parser_id` | 分块方法 | 下拉选择 | `naive` | 决定文档如何被切分成 chunks |
| `embd_id` | 嵌入模型 | 下拉选择 | 租户默认模型 | 文本向量化使用的模型 |
| `similarity_threshold` | 相似度阈值 | 滑块 | `0.2` | 检索时过滤低于此分数的结果 |
| `vector_similarity_weight` | 向量权重 | 滑块 | `0.3` | 向量检索与关键词检索的混合权重 |
| `permission` | 可见范围 | 选择 | `me` | `me`=仅自己 / `team`=团队共享 |
| `pagerank` | PageRank | 输入 | `0` | 知识库的权威度分数 |

### 参数关系说明

```
最终检索得分 = vector_similarity_weight × 向量相似度 
            + (1 - vector_similarity_weight) × 关键词相似度

仅返回得分 > similarity_threshold 的结果
```

---

## 三、分块策略（Chunk Method）详解

选择合适的分块策略是影响检索质量的**最关键因素**：

| 分块策略 | parser_id | 适用场景 | 核心特点 |
|---------|-----------|---------|---------|
| **通用** | `naive` | 通用文档，最常用 | 基于 token 数 + 语义边界切分 |
| **论文** | `paper` | 学术论文 | 保留标题层级，摘要完整块，按章节合并 |
| **书籍** | `book` | 长篇书籍 | 按章节/段落层级切分 |
| **表格** | `excel` | Excel/CSV 表格 | 按行范围切分，field:value 格式 |
| ** QA 对** | `qa` | 问答对格式 | 保持 question-answer 配对 |
| **法规** | `laws` | 法律法规 | 保留条款层级结构 |
| **手册** | `manual` | 产品手册/操作手册 | 按章节层级，保留编号 |
| **演示文稿** | `presentation` | PPT 演示文稿 | 按幻灯片切分 |
| **简历** | `resume` | 个人简历 | 识别简历特有结构 |
| **整文档** | `one` | 短文档/需要全文上下文 | 整个文档不切分，一个 chunk |
| **图片** | `picture` | 纯图片文档 | Vision LLM 描述图片 |
| **邮件** | `email` | 电子邮件 | 保留邮件头/正文/附件结构 |
| **知识图谱** | `knowledge_graph` | 构建知识图谱 | 分块用 naive，后续走 GraphRAG |
| **标签** | `tag` | 标签提取 | 提取文档标签 |

### 分块策略选择指南

```
你的文档是什么类型？
    │
    ├── 学术论文 ─────────────▶ paper
    │
    ├── Excel/CSV/表格 ───────▶ table
    │
    ├── 产品手册/操作指南 ─────▶ manual
    │
    ├── 法律法规 ─────────────▶ laws
    │
    ├── 问答对 ───────────────▶ qa
    │
    ├── 长篇书籍 ─────────────▶ book
    │
    ├── PPT ──────────────────▶ presentation
    │
    ├── 短文档/需要全文理解 ───▶ one
    │
    └── 不确定/通用文档 ──────▶ naive（默认推荐）
```

---

## 四、解析配置（parser_config）详解

### 4.1 布局识别方法（layout_recognize）

**UI 位置**：知识库设置 → 解析方法 → 布局识别

| 选项 | 说明 | 适用场景 |
|------|------|---------|
| **DeepDOC**（默认） | RAGFlow 内置深度文档理解引擎 | 通用 PDF，推荐首选 |
| **Plain Text** | 纯文本提取，无 OCR | 文本型 PDF（非扫描件） |
| **Docling** | IBM Docling 文档转换库 | 需要 `USE_DOCLING=true` 启用 |
| **TCADP Parser** | 腾讯云文档智能解析 API | 需要 API 密钥 |
| **@MinerU** | MinerU 多模态解析 | 需要配置 MinerU API |
| **@PaddleOCR** | PaddleOCR-VL 视觉语言模型 | 需要配置 PaddleOCR API |
| **其他 LLM 模型** | Image2Text / OCR 模型 | 需要配置对应模型 |

**DeepDOC 与其他引擎的对比**：

| 特性 | DeepDOC | Plain Text | Docling | MinerU | PaddleOCR-VL |
|------|---------|------------|---------|--------|-------------|
| OCR 支持 | ✅ PaddleOCR | ❌ | ✅ | ✅ | ✅ VLM |
| 布局分析 | ✅ ONNX CNN | ❌ | ✅ | ✅ | ✅ VLM |
| 表格识别 | ✅ ONNX | ❌ | ✅ | ✅ | ✅ |
| 图片提取 | ✅ | ❌ | ✅ | ✅ | ✅ |
| 离线运行 | ✅ | ✅ | ✅ | 需 API | 需 API |
| 中文支持 | ✅ 优秀 | 一般 | ✅ | ✅ | ✅ |
| 推荐场景 | 通用首选 | 简单文档 | 结构化文档 | 复杂版面 | 极复杂版面 |

### 4.2 分块大小（chunk_token_num）

**UI 位置**：知识库设置 → 解析方法 → 分块大小

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| `chunk_token_num` | `512` | 1–2048 | 每个 chunk 的目标 token 数 |

**调试建议**：

| chunk_token_num | 适用场景 | 优缺点 |
|----------------|---------|--------|
| **128-256** | 精确检索、事实性问答 | 检索精度高，但可能丢失上下文 |
| **512**（默认） | 通用场景 | 平衡精度与上下文 |
| **1024-2048** | 需要长上下文理解 | 上下文完整，但检索精度可能下降 |

```
选择参考：
- 工业专利/技术文档 → 256-512（精确匹配部件名称和参数）
- 论文摘要/结论 → 512-1024（保持语义完整性）
- 产品手册 FAQ → 128-256（精确定位答案）
```

### 4.3 分隔符（delimiter）

**UI 位置**：知识库设置 → 解析方法 → 分隔符

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `delimiter` | `\n` | 用于切分 chunk 的分隔符 |

**自定义分隔符示例**：

```
\n                — 按换行切分（默认）
\n\n              — 按段落切分
。；！？\n        — 按中英文句号、分号、感叹号、问号切分
\n!?;。；！？     — 按常见标点和换行切分
---               — 按 Markdown 分割线切分
```

**子分隔符（enable_children）**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `enable_children` | `false` | 启用层级分隔 |
| `children_delimiter` | `\n` | 子层级分隔符 |

启用后，先按主分隔符切分，再按子分隔符进一步细分，适合层级结构文档。

### 4.4 任务页数（task_page_size）

**UI 位置**：知识库设置 → 解析方法 → 任务页数

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| `task_page_size` | `12` | ≥ 1 | 每个解析任务处理的页数 |

**影响**：
- 值越小 → 并行度越高，但跨页上下文越少
- 值越大 → 单任务处理更多页，跨页连贯性越好，但并行度降低

**不同 parser_id 的默认值**：

| parser_id | 默认 task_page_size | 说明 |
|-----------|-------------------|------|
| `paper` | 22 | 论文需要更大上下文 |
| `one` / `knowledge_graph` | ∞（整文档） | 必须完整上下文 |
| 其他 | 12 | 默认值 |

### 4.5 自动关键词与问题生成

**UI 位置**：知识库设置 → 解析方法

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| `auto_keywords` | `0` | 0–32 | 每个 chunk 自动生成的关键词数量 |
| `auto_questions` | `0` | 0–10 | 每个 chunk 自动生成的检索问题数 |

**效果说明**：

```
auto_keywords = 3 时，每个 chunk 会额外生成 3 个关键词
→ 存储在 important_kwd 字段
→ 检索时关键词匹配得分更高

auto_questions = 2 时，每个 chunk 会额外生成 2 个问题
→ 存储在 question_kwd 字段
→ 用户提问时问题匹配得分更高
```

**调试建议**：
- 开启 auto_keywords（3-5个）：提升关键词检索精度
- 开启 auto_questions（2-3个）：提升问答匹配度
- **注意**：开启后会增加 LLM 调用成本和解析时间

### 4.6 TOC 目录提取

**UI 位置**：知识库设置 → 解析方法 → 目录提取

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `toc_extraction` | `false` | 启用自动生成目录 |

**限制**：
- 仅对 `naive` 分块策略有效
- 启用后会将整个文档作为单个任务处理（`task_page_size = ∞`）
- 使用 LLM 生成层次化目录
- 目录作为特殊 chunk 存储，提升结构化检索效果

### 4.7 Excel 转 HTML

**UI 位置**：知识库设置 → 解析方法 → Excel 转 HTML

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `html4excel` | `false` | 将 Excel 表格转换为 HTML 格式存储 |

**效果**：
- 关闭：表格以 field:value 键值对文本形式存储
- 开启：表格以 HTML `<table>` 格式存储，保留表格结构
- **推荐**：复杂表格开启，简单表格关闭

### 4.8 图表上下文窗口

**UI 位置**：知识库设置 → 解析方法

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| `image_table_context_window` | `0` | 0–256 | 图表周围的上下文 token 数 |

当文档包含图片/表格时，此参数控制将图片/表格周围的多少文本作为上下文一起存储。设为 0 表示不附加上下文。

---

## 五、RAPTOR 层级摘要配置

RAPTOR（Recursive Abstractive Processing for Tree-Organized Retrieval）通过递归层级摘要增强检索。

**UI 位置**：知识库设置 → RAPTOR

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| `use_raptor` | `false` | 开关 | 启用 RAPTOR |
| `scope` | `file` | `file`/`dataset` | 摘要范围：单文件 or 整个知识库 |
| `max_token` | `256` | 0–2048 | 每个摘要节点的最大 token 数 |
| `threshold` | `0.1` | 0.0–1.0 | 聚类相似度阈值（越小聚类越细） |
| `max_cluster` | `64` | 1–1024 | 最大聚类数量 |
| `random_seed` | `0` | ≥ 0 | 随机种子（控制可重复性） |
| `prompt` | （内置模板） | 文本域 | 摘要生成的 Prompt 模板 |

**工作原理**：

```
原始 chunks (Level 0)
    │  相似度聚类
    ▼
簇 A → 摘要  ─┐
簇 B → 摘要  ─┤  Level 1
簇 C → 摘要  ─┘
    │  再次聚类
    ▼
超级簇 → 摘要  ──  Level 2
    │  继续...
    ▼
最终摘要  ──  Level N (根节点)
```

**调试建议**：
- 简单文档：不需要 RAPTOR
- 复杂长文档：启用 `scope=file`，`threshold=0.1`，`max_cluster=64`
- 知识库级摘要：启用 `scope=dataset`

> **注意**：RAPTOR 对结构化数据（表格、代码）效果有限，可通过 `auto_disable_for_structured_data=true` 自动跳过。

---

## 六、GraphRAG 知识图谱配置

GraphRAG 通过实体-关系抽取构建知识图谱，增强多跳推理能力。

**UI 位置**：知识库设置 → GraphRAG

| 参数 | 默认值 | 范围 | 说明 |
|------|--------|------|------|
| `use_graphrag` | `false` | 开关 | 启用 GraphRAG |
| `method` | `light` | `light`/`general` | 轻量级 or 通用模式 |
| `entity_types` | 见下方 | 标签列表 | 要抽取的实体类型 |
| `community` | `false` | 开关 | 启用社区检测 |
| `resolution` | `false` | 开关 | 启用实体消歧 |

**默认实体类型**：

```json
["organization", "person", "geo", "event", "category"]
```

**可自定义实体类型**（根据领域调整）：

```
工业文档推荐：
["organization", "person", "geo", "event", "category", 
 "component", "material", "process", "parameter", "standard"]

专利文档推荐：
["inventor", "assignee", "patent_number", "classification", 
 "claim", "component", "technique", "application"]
```

**method 对比**：

| 模式 | 特点 | 适用场景 |
|------|------|---------|
| `light` | 快速抽取，实体和关系较少 | 通用场景，资源有限 |
| `general` | 完整抽取，实体关系更丰富 | 复杂文档，需要深度推理 |

---

## 七、检索参数调试

### 相似度阈值

| 参数 | 默认值 | 调试方向 |
|------|--------|---------|
| `similarity_threshold` | `0.2` | 降低 → 返回更多结果（可能有噪音）<br>升高 → 返回更精确的结果（可能遗漏） |

### 向量/关键词权重比

| 参数 | 默认值 | 调试方向 |
|------|--------|---------|
| `vector_similarity_weight` | `0.3` | 升高 → 更依赖语义向量检索<br>降低 → 更依赖关键词精确匹配 |

```
典型调优场景：

场景1：技术文档精确检索（如专利查询）
  → similarity_threshold = 0.3
  → vector_similarity_weight = 0.2（偏关键词匹配）

场景2：语义理解问答
  → similarity_threshold = 0.1
  → vector_similarity_weight = 0.7（偏语义理解）

场景3：混合检索（推荐起点）
  → similarity_threshold = 0.2
  → vector_similarity_weight = 0.3（默认值）
```

---

## 八、MinerU 与 PaddleOCR 子参数

### MinerU 子参数

当 `layout_recognize` 选择含 `@MinerU` 的选项时显示：

| 参数 | 默认值 | 可选值 | 说明 |
|------|--------|--------|------|
| `mineru_parse_method` | `auto` | `auto`/`txt`/`ocr` | 解析方法：自动/文本/OCR |
| `mineru_formula_enable` | `true` | 开关 | 启用公式识别 |
| `mineru_table_enable` | `true` | 开关 | 启用表格识别 |
| `mineru_lang` | `English` | 19 种语言 | 文档语言 |

**支持的语言**：English、Chinese、Japanese、Korean、French、German、Russian、Arabic、Hindi、Thai、Vietnamese、Italian、Portuguese、Spanish、Dutch、Turkish、Polish、Czech、Swedish

### PaddleOCR 子参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `paddleocr_api_url` | — | PaddleOCR API 地址 |
| `paddleocr_access_token` | — | API 访问令牌 |
| `paddleocr_algorithm` | `PaddleOCR-VL` | 算法选择 |

---

## 九、文档级别参数覆盖

上传文档时，可以覆盖知识库的默认配置：

**支持覆盖的参数**：

| 参数 | 说明 |
|------|------|
| `parser_id` | 为单个文档指定不同的分块策略 |
| `pages` | 指定解析的页范围（如 `[[1, 5], [10, 15]]`） |
| `chunk_token_num` | 覆盖分块大小 |
| `layout_recognize` | 覆盖布局识别方法 |
| `task_page_size` | 覆盖任务页数 |
| `delimiter` | 覆盖分隔符 |
| `auto_keywords` | 覆盖自动关键词数 |
| `auto_questions` | 覆盖自动问题数 |
| `html4excel` | 覆盖 Excel 转 HTML |
| `toc_extraction` | 覆盖目录提取 |
| `image_table_context_window` | 覆盖图表上下文 |

**典型用法**：
- 知识库中有多种类型文档时，为每种类型单独配置
- 某些特殊页面需要跳过时，用 `pages` 指定范围
- 同一文档的不同部分需要不同分块策略时

---

## 十、工业 PDF 调优实战方案

### 场景：低质量工业 PDF（如 IMDR 数据集）

**问题特征**：
- 低分辨率、扫描件型 PDF
- 复杂版面（表格、图表、公式混排）
- 中文技术文档
- 图文交错

### 推荐调优方案

#### 方案一：DeepDOC + 精确检索（推荐）

```
分块策略: naive
布局识别: DeepDOC
分块大小: 256
分隔符: \n
任务页数: 12
自动关键词: 5
自动问题: 3
similarity_threshold: 0.3
vector_similarity_weight: 0.2
```

#### 方案二：论文类文档

```
分块策略: paper
布局识别: DeepDOC
分块大小: 512
任务页数: 22
自动关键词: 3
similarity_threshold: 0.2
vector_similarity_weight: 0.3
```

#### 方案三：极复杂版面（使用 MinerU）

```
分块策略: naive
布局识别: @MinerU
MinerU 解析方法: auto
MinerU 公式识别: 开启
MinerU 表格识别: 开启
MinerU 语言: Chinese
分块大小: 512
自动关键词: 5
```

#### 方案四：需要深度推理的文档

```
分块策略: one（整文档）
布局识别: DeepDOC
启用 RAPTOR: 是（scope=file, threshold=0.1）
启用 GraphRAG: 是（method=light）
similarity_threshold: 0.1
vector_similarity_weight: 0.5
```

### 调优迭代流程

```
Step 1: 使用默认配置上传文档 → 测试检索效果
    │
    ▼ 效果不理想
Step 2: 调整 chunk_token_num（256/512/1024）→ 重新解析 → 测试
    │
    ▼ 仍有问题
Step 3: 切换 layout_recognize（DeepDOC → MinerU）→ 重新解析 → 测试
    │
    ▼ 检索精度不足
Step 4: 调整 similarity_threshold 和 vector_similarity_weight → 测试
    │
    ▼ 需要更多上下文
Step 5: 启用 RAPTOR / GraphRAG → 重新处理 → 测试
    │
    ▼ 达到满意效果
Step 6: 固定配置，记录最佳参数组合
```

### 关键注意事项

1. **每次修改参数后必须重新解析文档**，修改知识库参数不会自动重新处理已上传的文档
2. **auto_keywords 和 auto_questions** 会增加 LLM 调用成本，生产环境按需开启
3. **GraphRAG 和 RAPTOR** 需要额外的 Chat LLM 模型支持
4. **切换 layout_recognize 后需要全量重新解析**，不同引擎的输出格式不兼容
5. **task_page_size 过大**可能导致单任务超时（默认 3 小时超时），复杂文档建议保持 12

---

> **参考资源**：
> - RAGFlow GitHub：https://github.com/infiniflow/ragflow
> - RAGFlow 文档：https://ragflow.io/docs
> - RAPTOR 论文：https://arxiv.org/abs/2401.18059
> - GraphRAG 论文：https://arxiv.org/abs/2404.16130
