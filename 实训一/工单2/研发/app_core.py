"""共享 QA 系统初始化逻辑"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from document_loader import prepare_documents
from embedding import RAGRetriever
from query_processor import QueryProcessor
from llm_agent import QASystem
from config import PDF_PATH, FAISS_INDEX_PATH

_qa_system = None


def get_qa_system() -> QASystem:
    """懒加载并缓存问答系统实例"""
    global _qa_system
    if _qa_system is not None:
        return _qa_system

    retriever = RAGRetriever()
    query_processor = QueryProcessor()
    index_path = os.path.join(FAISS_INDEX_PATH, "faiss.index")

    if os.path.exists(index_path):
        retriever.load_from_index()
    else:
        chunks = prepare_documents(PDF_PATH)
        retriever.initialize(chunks)

    _qa_system = QASystem(retriever, query_processor)
    return _qa_system


def get_doc_info() -> dict:
    """返回当前知识库文档信息"""
    path = Path(PDF_PATH)
    if not path.is_file():
        return {"name": "招股说明书", "type": "PDF", "size_mb": 0, "exists": False}

    size_mb = path.stat().st_size / (1024 * 1024)
    return {
        "name": path.stem,
        "filename": path.name,
        "type": "PDF",
        "size_mb": round(size_mb, 2),
        "exists": True,
    }
