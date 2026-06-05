# ⚡ 快速参考卡

## 🚀 快速启动

### Windows
```bash
run.bat
# 然后选择启动方式
```

### Linux/Mac
```bash
bash run.sh
# 或
chmod +x run.sh && ./run.sh
```

### 直接命令
```bash
# 命令行模式(推荐)
python 1.py

# Web界面
streamlit run ui_app.py

# 单个查询
python 1.py "您的问题"

# 批量查询
python 1.py --batch queries.txt
```

---

## 📋 常用命令

| 场景 | 命令 |
|------|------|
| 启动系统 | `python 1.py` |
| Web界面 | `streamlit run ui_app.py` |
| 查询示例 | `python 1.py "公司财务状况?"` |
| 批量处理 | `python 1.py --batch queries.txt` |
| 项目初始化 | `python setup.py` |
| 系统测试 | `python test_system.py` |
| 完整测试 | `python test_system.py --all` |
| API测试 | `python test_system.py --api` |

---

## 🎯 核心功能

### Query理解
```python
from query_processor import QueryProcessor
processor = QueryProcessor()
result = processor.process_query("问题")
# 返回:意图、子查询、实体
```

### 文档处理
```python
from document_loader import prepare_documents
chunks = prepare_documents("path/to/pdf")
```

### 向量检索
```python
from embedding import RAGRetriever
retriever = RAGRetriever()
retriever.initialize(chunks)
results = retriever.retrieve("查询")
```

### 答案生成（同步）
```python
from llm_agent import QASystem
qa_system = QASystem(retriever, query_processor)
result = qa_system.answer("问题", lang="zh", history=None)
# history 为可选的多轮对话历史
```

### 答案生成（流式）
```python
from llm_agent import QASystem
qa_system = QASystem(retriever, query_processor)
metadata, content_gen = qa_system.answer_stream("问题", lang="zh", history=None)
for chunk in content_gen:
    print(chunk, end="", flush=True)
```

---

## ⚙️ 关键参数

| 参数 | 位置 | 说明 | 推荐值 |
|------|------|------|--------|
| `CHUNK_SIZE` | config.py | 文本块大小 | 800 |
| `CHUNK_OVERLAP` | config.py | 块重叠 | 100 |
| `TOP_K` | config.py | 检索数量 | 5 |
| `TEMPERATURE` | config.py | 答案多样性 | 0.7 |
| `MAX_TOKENS` | config.py | 最大生成长度 | 1000 |
| `history` | answer() | 多轮对话历史（最近10轮） | None |
| `stream` | API | 流式输出（/api/chat/stream） | false |
| `SIMILARITY_THRESHOLD` | config.py | 相似度阈值 | 0.3 |

### 参数调优建议
```
财务数据查询:TEMPERATURE=0.3(确定)
一般查询:TEMPERATURE=0.7(平衡)
创意问题:TEMPERATURE=0.9(随机)

准确度低:增加TOP_K到7-10
速度慢:减少TOP_K到2-3
内存多:减少CHUNK_SIZE到600
```

---

## 🔍 问答示例

### 示例1:财务查询
```
Q: 公司2023年营业收入是多少?
Expected: ✓ 精准财务数据
Tips: 输入具体的财务指标名称
```

### 示例2:风险分析
```
Q: 公司面临的主要风险有哪些?
Expected: ✓ 多个风险因素列表
Tips: 系统会自动分析多个相关段落
```

### 示例3:产品介绍
```
Q: 请介绍公司的主要产品
Expected: ✓ 产品列表和描述
Tips: 问题越具体,答案质量越高
```

---

## 🐛 快速排查

| 问题 | 原因 | 解决 |
|------|------|------|
| PDF加载失败 | 文件路径错误 | `mkdir data && cp pdf data/` |
| API连接失败 | 密钥错误 | 检查config.py中的API_KEY |
| 答案不准确 | 参数设置不佳 | 调整TOP_K, TEMPERATURE |
| 系统很慢 | 索引未缓存 | 等待首次运行完成 |
| 内存溢出 | 文件太大 | 减少CHUNK_SIZE |

---

## 📁 重要文件

```
1.py              ⭐ 主程序
ui_app.py         🎨 Web界面
config.py         ⚙️ 配置文件
README.md         📖 完整文档
TUTORIAL.md       📚 详细教程
```

---

## 🔗 重要链接

- 📖 完整文档:`README.md`
- 📚 详细教程:`TUTORIAL.md`
- 🏗️ 项目结构:`PROJECT_STRUCTURE.md`
- ⚙️ 配置说明:`config.py`
- 🧪 测试工具:`test_system.py`

---

## 💡 快速提示

✅ **做这些**
- 将问题具体化
- 查看参考来源
- 调整参数测试
- 查看系统状态

❌ **避免这些**
- 问题太模糊
- 盲目增加TOP_K
- 在不理解的情况下修改参数
- 忽视置信度指标

---

## 🎓 学习路径

1. **快速开始** → 运行 `python 1.py`
2. **了解结构** → 阅读 `README.md`
3. **深入学习** → 学习 `TUTORIAL.md`
4. **自定义开发** → 编辑各个模块
5. **性能优化** → 调整 `config.py` 参数

---

## 📞 获取帮助

- 查看TUTORIAL.md常见问题区
- 运行test_system.py诊断
- 检查项目README和文档
- 查看代码注释

---

**最后更新**：2024-05-27  
**版本**：1.1.0（新增多轮对话 + 流式输出）
