# 📁 项目文件结构说明

## 完整项目结构

```
招股说明书问答系统/
│
├── 📄 1.py                       ⭐ 【主程序】命令行入口（推荐）
│   └── 功能：交互式问答、单个查询、批量处理
│
├── 🎨 ui_app.py                  【Web界面】Streamlit应用
│   └── 功能：友好的Web UI，包含问答、演示、状态等
│
├── ⚙️ config.py                  【配置文件】系统参数配置
│   └── API密钥、模型参数、数据路径等
│
├── 🧠 query_processor.py         【Query理解】问题分析模块
│   ├─ 意图识别（财务、产品、风险等）
│   ├─ 问题分解（复杂问题拆分）
│   └─ 实体抽取（时间、金额、关键词）
│
├── 📄 document_loader.py         【文档处理】PDF读取和分块
│   ├─ DocumentLoader: PDF加载
│   ├─ TextChunker: 文本分块
│   └─ prepare_documents: 一体化处理
│
├── 🔢 embedding.py               【向量检索】嵌入和FAISS检索
│   ├─ EmbeddingManager: 文本向量化
│   ├─ FAISSRetriever: FAISS索引和检索
│   └─ RAGRetriever: 综合检索管理
│
├── 🤖 llm_agent.py               【LLM代理】答案生成
│   ├─ DeepSeekLLM: API调用
│   ├─ RAGGenerator: RAG答案生成
│   └─ QASystem: 完整问答系统
│
├── 🚀 setup.py                   【初始化】项目环境配置
│   └── 功能：一键初始化项目
│
├── 📋 requirements.txt            【依赖列表】Python包依赖
│
├── 🚀 run.bat                     【启动脚本】Windows快速启动
├── 🚀 run.sh                      【启动脚本】Linux/Mac快速启动
│
├── 📖 README.md                  【项目文档】完整说明和使用指南
├── 📖 TUTORIAL.md                【详细教程】功能演示和问题解答
├── 📖 PROJECT_STRUCTURE.md       【本文件】文件结构说明
│
├── .env                          【环境变量】API密钥配置
├── .gitignore                    【Git配置】忽略文件列表
│
├── 📁 data/                      【数据目录】
│   ├── 招股说明书1-无水印.pdf        原始PDF文档
│   └── faiss_index/              向量索引（自动生成）
│       ├── faiss.index           FAISS索引文件
│       └── chunks.pkl            文本块缓存
│
├── 📁 results/                   【结果目录】
│   ├── queries_results.txt       查询结果
│   └── analysis_report.md        分析报告
│
└── 📁 __pycache__/              【缓存】Python字节码（自动生成）
```

---

## 核心文件详解

### 🌟 核心模块 (5个)

| 文件 | 功能 | 关键类/函数 |
|------|------|-----------|
| `query_processor.py` | Query理解 | `QueryProcessor.process_query()` |
| `document_loader.py` | 文档加载 | `prepare_documents()` |
| `embedding.py` | 向量检索 | `RAGRetriever.retrieve()` |
| `llm_agent.py` | 答案生成 | `QASystem.answer()` |
| `config.py` | 系统配置 | 所有配置参数 |

### 📱 应用程序 (2个)

| 文件 | 类型 | 使用场景 |
|------|------|---------|
| `1.py` | 命令行应用 | 推荐使用，支持交互、单查询、批处理 |
| `ui_app.py` | Web应用 | 最友好，支持演示查询、系统状态查看 |

### 🛠️ 工具脚本 (2个)

| 文件 | 平台 | 功能 |
|------|------|------|
| `run.bat` | Windows | 快速启动向导 |
| `run.sh` | Linux/Mac | 快速启动向导 |
| `setup.py` | 通用 | 项目初始化 |

### 📚 文档 (3个)

| 文件 | 内容 |
|------|------|
| `README.md` | 项目总览、功能介绍、快速开始 |
| `TUTORIAL.md` | 详细教程、API说明、常见问题 |
| `PROJECT_STRUCTURE.md` | 本文件，项目结构说明 |

---

## 使用场景对应文件

### 场景1: "我想快速试用系统"
```
1.py  →  命令行交互
    ↓
document_loader.py  →  加载PDF
    ↓
embedding.py  →  建立索引
    ↓
query_processor.py  →  理解问题
    ↓
llm_agent.py  →  生成答案
```

### 场景2: "我想开发或修改系统"
```
查看：README.md  →  理解架构
    ↓
修改：config.py  →  调整参数
    ↓
编辑：各个模块  →  定制功能
    ↓
测试：1.py  →  验证效果
```

### 场景3: "我想给非技术人员展示"
```
启动：ui_app.py  →  Streamlit Web界面
    ↓
演示：预设查询  →  展示功能
    ↓
反馈：用户输入  →  自定义查询
```

---

## 数据流转图

```
用户输入问题
    ↓
┌─────────────────────────────────────┐
│ 1.py / ui_app.py (应用层)           │
│ 负责：用户交互、结果展示             │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│ query_processor.py (理解层)          │
│ 负责：意图识别、分解、实体抽取      │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│ embedding.py (检索层)                │
│ 负责：向量化、FAISS检索              │
└──────────────┬──────────────────────┘
               ↓
┌─────────────────────────────────────┐
│ llm_agent.py (生成层)                │
│ 负责：LLM调用、答案生成              │
└──────────────┬──────────────────────┘
               ↓
            最终答案
```

---

## 文件大小参考

| 文件 | 大小 | 说明 |
|------|------|------|
| config.py | ~2KB | 配置文件 |
| query_processor.py | ~5KB | Query处理 |
| document_loader.py | ~8KB | 文档处理 |
| embedding.py | ~12KB | 向量检索 |
| llm_agent.py | ~15KB | LLM代理 |
| ui_app.py | ~20KB | Web界面 |
| 1.py | ~12KB | 命令行应用 |
| **总计(代码)** | **~74KB** | |
| 招股说明书PDF | 数MB~数十MB | 根据实际文件 |
| FAISS索引 | 数十MB~数百MB | 根据PDF大小 |

---

## 文件读写操作

### 读取文件
```
1.py, ui_app.py
    ↓
document_loader.py  →  读取 data/*.pdf
    ↓
embedding.py  →  读取 data/faiss_index/*
    ↓
config.py  →  读取配置
```

### 写入文件
```
document_loader.py  →  处理PDF
    ↓
embedding.py  →  生成 data/faiss_index/
    ↓
1.py  →  生成 results/*.txt
```

---

## 扩展与定制

### 添加新的Query处理逻辑
编辑：`query_processor.py`
- 添加新的意图类型
- 自定义分解规则
- 扩展实体抽取

### 切换不同的LLM
编辑：`llm_agent.py`
```python
class YourLLM:
    def generate(self, prompt):
        # 你的LLM实现
        pass
```

### 优化检索性能
编辑：`embedding.py` 和 `config.py`
- 更换嵌入模型
- 调整块大小
- 使用GPU加速

### 自定义UI风格
编辑：`ui_app.py`
- 修改Streamlit CSS
- 调整布局
- 添加新功能

---

## 目录权限要求

```
data/              → 可读写（存储PDF和索引）
results/           → 可写（存储结果）
__pycache__/       → 自动管理
venv/              → 虚拟环境（独立管理）
```

---

## 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0.0 | 2024-05-22 | 初始版本 |

---

## 快速导航

- 🚀 **快速开始**：见 [README.md](README.md)
- 📖 **详细教程**：见 [TUTORIAL.md](TUTORIAL.md)
- ⚙️ **参数调优**：见 [config.py](config.py)
- 🤔 **常见问题**：见 [TUTORIAL.md](TUTORIAL.md#常见问题)

---

**最后更新**：2024年5月22日
