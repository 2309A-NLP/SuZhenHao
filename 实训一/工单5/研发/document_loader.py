"""
文档加载和处理模块 - 支持多 PDF 文件的读取和分块
"""
import gc
import os
from typing import Dict, List, Optional

import PyPDF2
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from config import CHUNK_OVERLAP, CHUNK_SIZE, PDF_DIR


class DocumentLoader:
    """文档加载器，支持单个或多个 PDF。"""

    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.documents = []

    def _extract_with_pypdf2(self) -> List[str]:
        texts = []
        metadata = []
        with open(self.pdf_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            if getattr(reader, "is_encrypted", False):
                try:
                    reader.decrypt("")
                except Exception:
                    pass

            total_pages = len(reader.pages)
            for page_num, page in enumerate(reader.pages):
                text = page.extract_text()
                if text:
                    texts.append(text)
                    metadata.append({"page": page_num + 1, "total_pages": total_pages})
        self.documents = [{"text": text, "metadata": meta} for text, meta in zip(texts, metadata)]
        return texts

    def load_pdf(self) -> List[str]:
        """加载 PDF 文件并提取文本。"""
        if not os.path.exists(self.pdf_path):
            raise FileNotFoundError(f"PDF文件未找到: {self.pdf_path}")

        texts = []
        metadata = []

        if pdfplumber:
            try:
                with pdfplumber.open(self.pdf_path) as pdf:
                    total_pages = len(pdf.pages)
                    for page_num, page in enumerate(pdf.pages):
                        text = page.extract_text()
                        if text:
                            texts.append(text)
                            metadata.append({"page": page_num + 1, "total_pages": total_pages})

                self.documents = [{"text": text, "metadata": meta} for text, meta in zip(texts, metadata)]
                return texts
            except Exception:
                texts = []
                metadata = []

        try:
            return self._extract_with_pypdf2()
        except Exception as exc:
            msg = str(exc)
            if "PyCryptodome is required for AES algorithm" in msg or "DependencyError" in msg:
                raise RuntimeError(
                    "PDF 为加密文件，当前环境缺少 PyCryptodome，无法解密读取。"
                ) from exc
            raise

    def get_documents(self) -> List[Dict]:
        return self.documents


class TextChunker:
    """文本分块器。"""

    def __init__(self, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text: str, page_num: int = None) -> List[Dict]:
        if not text or len(text) < 10:
            return []

        chunks = []
        text_len = len(text)
        start = 0
        chunk_id_local = 0

        while start < text_len:
            end = min(start + self.chunk_size, text_len)

            if end < text_len:
                last_space = text.rfind(" ", start, end)
                if last_space > start + self.chunk_size // 2:
                    end = last_space

            chunk_text = text[start:end].strip()

            if chunk_text and len(chunk_text) > 10:
                chunks.append(
                    {
                        "content": chunk_text,
                        "page": page_num,
                        "start_pos": start,
                        "end_pos": end,
                        "_local_id": chunk_id_local,
                    }
                )
                chunk_id_local += 1

            if end >= text_len:
                break

            next_start = end - self.overlap
            start = max(next_start, end)
            if start == end:
                start = min(end + self.chunk_size // 2, text_len)

        return chunks

    def chunk_documents(self, documents: List[Dict]) -> List[Dict]:
        all_chunks = []
        chunk_id = 0

        total_docs = len(documents)
        for doc_idx, doc in enumerate(documents):
            doc_text = doc.get("text", "")
            if not doc_text:
                continue

            chunks = self.chunk_text(doc_text, doc["metadata"].get("page"))
            for chunk in chunks:
                chunk["chunk_id"] = chunk_id
                chunk["metadata"] = doc["metadata"]
                # 标记来源文件
                chunk["source"] = doc["metadata"].get("source", "unknown")
                all_chunks.append(chunk)
                chunk_id += 1

            if (doc_idx + 1) % 50 == 0:
                gc.collect()

        gc.collect()
        return all_chunks


def prepare_documents(pdf_paths: Optional[List[str]] = None, pdf_dir: str = PDF_DIR) -> List[Dict]:
    """准备文档，支持单个或多个 PDF 文件。

    Args:
        pdf_paths: PDF 文件名列表（不含目录前缀）。为 None 时使用 config.PDF_FILES。
        pdf_dir: PDF 所在目录。
    """
    if pdf_paths is None:
        from config import PDF_FILES
        pdf_paths = PDF_FILES

    all_documents = []
    chunker = TextChunker()

    for pdf_name in pdf_paths:
        pdf_path = os.path.join(pdf_dir, pdf_name) if not os.path.isabs(pdf_name) else pdf_name
        if not os.path.exists(pdf_path):
            print(f"⚠️  跳过不存在的文件: {pdf_path}")
            continue

        print(f"📄 加载: {pdf_name}")
        loader = DocumentLoader(pdf_path)
        loader.load_pdf()
        documents = loader.get_documents()

        # 标记来源
        for doc in documents:
            doc["metadata"]["source"] = pdf_name

        all_documents.extend(documents)
        print(f"   ✓ {len(documents)} 页")

    if not all_documents:
        raise FileNotFoundError("没有成功加载任何 PDF 文件")

    print(f"\n🔪 分块中... (共 {len(all_documents)} 页)")
    chunks = chunker.chunk_documents(all_documents)
    print(f"✓ 分块完成，共 {len(chunks)} 个文本块")
    return chunks


def get_pdf_list(pdf_dir: str = PDF_DIR) -> List[Dict]:
    """获取 data/ 目录下所有 PDF 文件信息。"""
    pdfs = []
    if not os.path.exists(pdf_dir):
        return pdfs

    for f in sorted(os.listdir(pdf_dir)):
        if f.lower().endswith(".pdf"):
            path = os.path.join(pdf_dir, f)
            size_mb = os.path.getsize(path) / (1024 * 1024)
            pdfs.append({
                "name": f,
                "size_mb": round(size_mb, 2),
                "path": path,
            })
    return pdfs


def delete_pdf(filename: str, pdf_dir: str = PDF_DIR) -> bool:
    """删除指定 PDF 文件。"""
    path = os.path.join(pdf_dir, filename)
    if os.path.exists(path) and filename.lower().endswith(".pdf"):
        os.remove(path)
        return True
    return False


if __name__ == "__main__":
    try:
        chunks = prepare_documents()
        if chunks:
            print(f"\n--- 共 {len(chunks)} 个文本块 ---")
            # 统计来源
            sources = set(c.get("source", "unknown") for c in chunks)
            print(f"来源文件: {sources}")
    except FileNotFoundError as exc:
        print(f"错误: {exc}")
