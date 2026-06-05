"""共享 QA 系统初始化逻辑 - 支持多 PDF 动态管理"""
import os
import sys
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from document_loader import prepare_documents, get_pdf_list, delete_pdf
from embedding import RAGRetriever
from query_processor import QueryProcessor
from llm_agent import QASystem
from config import FAISS_INDEX_PATH, PDF_DIR

_qa_system = None
_active_pdfs: Optional[List[str]] = None  # None = 使用全部


def get_active_pdfs() -> Optional[List[str]]:
    """获取当前激活的 PDF 列表。"""
    return _active_pdfs


def set_active_pdfs(pdf_names: Optional[List[str]]):
    """设置激活的 PDF 列表，None 表示全部。"""
    global _active_pdfs, _qa_system
    _active_pdfs = pdf_names
    # 清除缓存，下次调用会重建索引
    _qa_system = None
    # 删除旧索引
    _clear_index()


def _clear_index():
    """删除旧的 FAISS 索引文件。"""
    import shutil
    index_dir = FAISS_INDEX_PATH
    if os.path.exists(index_dir):
        shutil.rmtree(index_dir)


def get_qa_system(force_rebuild: bool = False) -> QASystem:
    """懒加载并缓存问答系统实例，支持多 PDF。"""
    global _qa_system
    if _qa_system is not None and not force_rebuild:
        return _qa_system

    retriever = RAGRetriever()
    query_processor = QueryProcessor()
    index_path = os.path.join(FAISS_INDEX_PATH, "faiss.index")

    if os.path.exists(index_path) and not force_rebuild:
        retriever.load_from_index()
    else:
        # 根据激活列表加载 PDF
        pdf_names = _active_pdfs
        chunks = prepare_documents(pdf_paths=pdf_names)
        retriever.initialize(chunks)

    _qa_system = QASystem(retriever, query_processor)
    return _qa_system


def get_doc_info() -> dict:
    """返回当前知识库文档信息（兼容旧接口）。"""
    from config import PDF_FILES
    # 返回第一个激活的 PDF 信息
    pdfs = _active_pdfs or PDF_FILES
    if not pdfs:
        return {"name": "招股说明书", "type": "PDF", "size_mb": 0, "exists": False}

    first = os.path.join(PDF_DIR, pdfs[0])
    path = Path(first)
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


def get_all_pdfs_info() -> List[dict]:
    """获取所有 PDF 文件信息及其激活状态。"""
    all_pdfs = get_pdf_list(PDF_DIR)
    active = _active_pdfs
    for pdf in all_pdfs:
        pdf["active"] = active is None or pdf["name"] in active
    return all_pdfs


def rebuild_index():
    """强制重建索引。"""
    global _qa_system
    _qa_system = None
    _clear_index()
    get_qa_system(force_rebuild=True)
