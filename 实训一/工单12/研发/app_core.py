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
from config import FAISS_INDEX_PATH, PDF_DIR, RETRIEVAL_MODE

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
    # 删除全部索引（PDF 变了，所有模式都要重建）
    _clear_index()


def _clear_index(mode: str = None):
    """删除索引文件。mode=None 时删除全部，否则只删除对应模式的文件。"""
    index_dir = FAISS_INDEX_PATH
    if not os.path.exists(index_dir):
        return

    if mode is None:
        # 删除全部
        import shutil
        shutil.rmtree(index_dir)
        return

    # 按模式删除，保留其他模式的索引
    files_to_delete = []
    if mode == "lightrag":
        from config import LIGHTRAG_GRAPH_PATH
        files_to_delete.append(LIGHTRAG_GRAPH_PATH)
    elif mode == "hybrid":
        files_to_delete.extend([
            os.path.join(index_dir, "faiss.index"),
            os.path.join(index_dir, "chunks.pkl"),
            os.path.join(index_dir, "bm25_data.pkl"),
        ])
    elif mode == "vector":
        files_to_delete.extend([
            os.path.join(index_dir, "faiss.index"),
            os.path.join(index_dir, "chunks.pkl"),
        ])
    elif mode == "bm25":
        files_to_delete.append(os.path.join(index_dir, "bm25_data.pkl"))

    for f in files_to_delete:
        if os.path.exists(f):
            os.remove(f)
            print(f"[清理] 已删除: {os.path.basename(f)}")


def get_qa_system(force_rebuild: bool = False, retrieval_mode: str = None) -> QASystem:
    """懒加载并缓存问答系统实例，支持多 PDF 和检索模式切换。"""
    global _qa_system

    mode = retrieval_mode or RETRIEVAL_MODE

    # 如果检索模式变了，需要重建
    if _qa_system is not None and not force_rebuild:
        if hasattr(_qa_system.retriever, 'retrieval_mode') and _qa_system.retriever.retrieval_mode == mode:
            return _qa_system
        # 检索模式变化，强制重建（不删除其他模式的索引）
        force_rebuild = True

    if force_rebuild:
        _qa_system = None

    retriever = RAGRetriever(retrieval_mode=mode)
    query_processor = QueryProcessor()

    # 判断索引是否存在（hybrid 模式需要同时有 faiss.index 和 bm25_data.pkl）
    index_exists = False
    if mode == "bm25":
        index_exists = os.path.exists(os.path.join(FAISS_INDEX_PATH, "bm25_data.pkl"))
    elif mode == "vector":
        index_exists = os.path.exists(os.path.join(FAISS_INDEX_PATH, "faiss.index"))
    elif mode == "hybrid":
        index_exists = (
            os.path.exists(os.path.join(FAISS_INDEX_PATH, "faiss.index"))
            and os.path.exists(os.path.join(FAISS_INDEX_PATH, "bm25_data.pkl"))
        )

    if mode == "lightrag":
        # LightRAG 模式需要 faiss.index + lightrag_graph.json
        from config import LIGHTRAG_GRAPH_PATH
        lightrag_index_exists = (
            os.path.exists(os.path.join(FAISS_INDEX_PATH, "faiss.index"))
            and os.path.exists(LIGHTRAG_GRAPH_PATH)
        )
        if lightrag_index_exists:
            # 索引存在，直接加载（秒切）
            retriever.load_from_index()
        else:
            # 索引不存在，需要构建
            print("[LightRAG] 索引文件不存在，开始构建...")
            pdf_names = _active_pdfs
            chunks = prepare_documents(pdf_paths=pdf_names)
            retriever.initialize(chunks)
    elif index_exists:
        # 索引存在，直接加载（秒切）
        retriever.load_from_index()
    else:
        # 索引不存在，需要构建
        print(f"[{mode}] 索引文件不存在，开始构建...")
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
