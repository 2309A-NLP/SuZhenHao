# 🦞 智能文档问答系统

基于 RAG + 知识图谱 + 语音识别的智能文档问答系统。

## ✨ 功能特性

- 📄 **PDF文档解析**：支持中英文PDF文档的文本提取和智能分块
- 💬 **智能问答**：基于RAG（检索增强生成）的精准问答
- 🕸️ **知识图谱**：自动抽取实体关系，交互式可视化展示
- 🎤 **语音输入**：支持语音提问，自动转文字
- 🌐 **中英文支持**：同时支持中文和英文文档及问答

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置API

编辑 `config.py` 文件，填入你的 MiMo API Key：

```python
MIMO_API_KEY = "你的API密钥"
```

### 3. 运行系统

```bash
streamlit run app.py
```

## 📁 项目结构

```
工单8/
├── app.py                  # 主界面（Streamlit）
├── config.py               # 配置文件
├── pdf_processor.py        # PDF处理模块
├── rag_chain.py            # RAG检索生成模块
├── knowledge_graph.py      # 知识图谱模块
├── speech.py               # 语音识别模块
├── requirements.txt        # 依赖清单
├── vector_store/           # 向量库存储目录
├── uploads/                # 上传的PDF文件
└── kg_output/              # 知识图谱HTML输出
```

## 🛠️ 技术栈

| 模块 | 技术 |
|------|------|
| PDF解析 | pdfplumber |
| 文本分块 | LangChain TextSplitter |
| 向量化 | sentence-transformers (bge-small-zh) |
| 向量库 | FAISS |
| LLM | 小米 MiMo-v2.5-pro |
| 知识图谱 | NetworkX + Pyvis |
| 语音识别 | OpenAI Whisper |
| 前端界面 | Streamlit |
