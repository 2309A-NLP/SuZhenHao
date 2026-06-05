# 📖 使用教程

## 目录
1. [快速开始](#快速开始)
2. [功能详解](#功能详解)
3. [API说明](#api说明)
4. [常见问题](#常见问题)

---

## 快速开始

### 步骤1：环境准备

```bash
# 克隆或下载项目
cd 实训一

# 创建虚拟环境
python -m venv venv
source venv/Scripts/activate  # Windows

# 安装依赖
pip install -r requirements.txt

# 或使用项目初始化脚本
python setup.py
```

### 步骤2：准备文件

```bash
# 创建数据目录
mkdir data

# 将招股说明书PDF放入data目录
# data/
#   └── 招股说明书1-无水印.pdf
```

### 步骤3：配置API

编辑 `config.py` 或 `.env`：
```python
DEEPSEEK_API_KEY = "sk-840d940fbe6647109da000608d2a011a"
```

### 步骤4：启动系统

#### 方式A：命令行交互（推荐初学者）
```bash
python 1.py
```

交互界面示例：
```
============================================================
🚀 RAG问答系统初始化
============================================================

[1/2] 加载PDF文件...
✓ 已加载第 1/100 页
✓ 已加载第 2/100 页
...
✓ 成功加载PDF，共 100 页

[2/2] 分割文本块...
✓ 分块完成，共生成 1000 个文本块

============================================================
✓ 系统初始化完成！
============================================================

📝 进入问答模式 (输入 'quit' 退出)
------------------------------------------------------------

👤 请输入您的问题: 公司2023年的收入是多少？

🔄 正在处理您的问题...
```

#### 方式B：命令行单查询
```bash
python 1.py "公司的主要业务是什么？"

# 输出示例：
# 📄 答案:
# 根据招股说明书，公司的主要业务包括...
#
# 📌 置信度: 87.5%
```

#### 方式C：Web界面（最友好）
```bash
streamlit run ui_app.py
```

然后打开浏览器访问 `http://localhost:8501`

![Web界面预览]
界面包含：
- 🤖 问答模块：输入问题，获取答案
- 📊 演示查询：预设的示例问题
- 📈 系统状态：查看系统运行状态
- 📖 使用指南：帮助文档

#### 方式D：批量处理
```bash
# 创建queries.txt文件
cat > queries.txt << EOF
公司2023年的收入是多少？
公司的主要产品有哪些？
公司面临的主要风险是什么？
EOF

# 执行批量处理
python 1.py --batch queries.txt

# 输出结果到 queries_results.txt
```

---

## 功能详解

### 1. Query理解模块

系统能够智能理解用户的问题：

```python
from query_processor import QueryProcessor

processor = QueryProcessor()

# 示例：分析问题
query = "公司2023年的财务状况和风险分析是什么？"
result = processor.process_query(query)

print(f"意图: {result['intent']}")
# 输出: 意图: 财务信息

print(f"子查询: {result['sub_queries']}")
# 输出: 子查询: ['公司2023年的财务状况是什么？', '风险分析是什么？']

print(f"关键实体: {result['entities']}")
# 输出: 关键实体: {'time': ['2023年'], 'number': [], 'keywords': [...]}
```

**识别的意图类型：**
- 📊 财务信息：收入、利润、资产等
- 🏢 公司信息：基本情况、管理团队等
- 🛍️ 产品服务：产品介绍、服务范围等
- ⚠️ 风险分析：风险因素、竞争风险等
- 🎯 发展战略：战略规划、投资方向等
- 📈 市场分析：市场规模、竞争情况等

### 2. 文档加载与分块

```python
from document_loader import prepare_documents

# 一步准备文档
chunks = prepare_documents("path/to/pdf")

# 返回示例
# [
#   {
#     'content': '文本内容...',
#     'page': 1,
#     'chunk_id': 0,
#     'metadata': {'total_pages': 100}
#   },
#   ...
# ]
```

**参数说明：**
- `CHUNK_SIZE = 800`：每个文本块的字符数
- `CHUNK_OVERLAP = 100`：块之间的重叠字符数

增加重叠可以提高检索准确度，但会增加计算量。

### 3. 向量检索

```python
from embedding import RAGRetriever

retriever = RAGRetriever()
retriever.initialize(chunks)

# 检索相关文档
results = retriever.retrieve("您的问题", k=5)

# 返回示例
# [
#   {
#     'chunk_id': 123,
#     'content': '相关文本...',
#     'page': 5,
#     'similarity': 0.87,
#     'distance': 2.34
#   },
#   ...
# ]
```

**相似度说明：**
- 0.0 = 完全不相关
- 0.5 = 部分相关
- 1.0 = 完全相关

### 4. 答案生成

```python
from llm_agent import QASystem

qa_system = QASystem(retriever, query_processor)

# 完整的问答流程
result = qa_system.answer("您的问题")

print(f"问题: {result['query']}")
print(f"答案: {result['answer']}")
print(f"置信度: {result['confidence']:.1%}")
print(f"来源: {result['sources']}")
```

**置信度计算：**
- 基于检索到的文档数量
- 基于最高相似度分数
- 综合评估答案的可靠性

---

## API说明

### DeepSeekLLM类

```python
from llm_agent import DeepSeekLLM

llm = DeepSeekLLM()

# 生成文本
answer = llm.generate(
    prompt="这是一个提示词",
    max_tokens=1000,
    temperature=0.7
)

# 测试连接
llm.test_connection()  # 返回 True/False
```

**参数说明：**
- `max_tokens`：最大生成令牌数（越大越详细）
- `temperature`：创意程度（0-1，0=确定，1=随机）

**调整建议：**
- 财务数据查询：`temperature=0.3`（确定）
- 风险分析：`temperature=0.5`（中等）
- 发展规划：`temperature=0.7`（创意）

### RAGRetriever类

```python
from embedding import RAGRetriever

retriever = RAGRetriever()

# 初始化系统
retriever.initialize(chunks)

# 检索
results = retriever.retrieve("查询", k=5)

# 从保存的索引加载
retriever.load_from_index()
```

### QueryProcessor类

```python
from query_processor import QueryProcessor

processor = QueryProcessor()

# 处理查询
result = processor.process_query("用户问题")
# 返回包含：意图、子查询、实体等

# 获取意图
intent = processor.get_intent("问题")

# 分解问题
sub_queries = processor.decompose_query("问题1 并且 问题2")

# 提取实体
entities = processor.extract_key_entities("2023年的收入100万")
```

---

## 常见问题

### Q1: 系统初始化很慢，怎么办？

**A:** 首次运行需要：
1. 下载嵌入模型（~200MB）
2. 处理PDF和嵌入向量（取决于PDF大小）
3. 构建FAISS索引

这是正常的。处理完成后，系统会保存索引，下次启动会快得多。

### Q2: 答案不准确，怎么改进？

**方案1：调整检索参数**
```python
# config.py
TOP_K = 7  # 增加检索文档数
SIMILARITY_THRESHOLD = 0.2  # 降低相似度阈值
CHUNK_SIZE = 600  # 减小块大小，提高粒度
```

**方案2：调整LLM参数**
```python
# 确定的答案
TEMPERATURE = 0.3
MAX_TOKENS = 800

# 更详细的答案
TEMPERATURE = 0.7
MAX_TOKENS = 1500
```

**方案3：优化提问**
- ❌ "公司怎么样？" → ✅ "公司2023年的营业收入是多少？"
- ❌ "说说风险" → ✅ "公司面临的主要风险因素有哪些？"

### Q3: API调用超出配额怎么办？

**A:** 
1. 检查使用情况：https://platform.deepseek.com
2. 增加API配额
3. 降低 `MAX_TOKENS` 和 `TOP_K`
4. 增加 `SIMILARITY_THRESHOLD` 过滤低质结果

### Q4: 如何使用本地LLM而不是API？

**A:** 修改 `llm_agent.py`，集成本地模型（如LLaMA2、Qwen等）：

```python
from transformers import pipeline

class LocalLLM:
    def __init__(self):
        self.pipe = pipeline(
            "text-generation",
            model="Qwen/Qwen-7B"
        )
    
    def generate(self, prompt, max_tokens=500, temperature=0.7):
        result = self.pipe(prompt, max_length=max_tokens)
        return result[0]['generated_text']
```

### Q5: 如何提高检索速度？

**A:**
```python
# 使用GPU加速FAISS
import faiss
index = faiss.index_factory(dimension, "GPU", faiss.METRIC_L2)

# 减少嵌入维度
EMBEDDINGS_MODEL = "sentence-transformers/all-MiniLM-L6-v2"  # 384维

# 减少文档数量
TOP_K = 3  # 默认5
```

### Q6: 如何导出或保存结果？

**A:**
```bash
# 方式1：使用批处理自动保存
python 1.py --batch queries.txt
# 结果保存到 queries_results.txt

# 方式2：手动保存
result = qa_system.answer("问题")
with open('result.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
```

### Q7: 支持多语言吗？

**A:** 
- ✅ 主要支持中文
- ✅ 也支持英文和其他语言
- ℹ️ 嵌入模型 `paraphrase-multilingual-MiniLM-L12-v2` 支持100+种语言
- ⚠️ DeepSeek API主要优化中英文

### Q8: 如何更新或重建索引？

**A:**
```bash
# 删除已保存的索引
rm -rf data/faiss_index

# 重新运行系统
python 1.py
# 系统会自动检测并重建索引
```

---

## 📞 获取帮助

- 📖 查看完整README: `README.md`
- 🐛 报告问题：GitHub Issues
- 💬 讨论：GitHub Discussions
- 📧 联系：support@example.com

---

**祝你使用愉快！** 🎉
