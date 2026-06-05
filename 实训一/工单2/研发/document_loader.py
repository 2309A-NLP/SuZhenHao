"""
文档加载和处理模块 - 处理 PDF 文件的读取和分块
"""
import gc
import os
from typing import Dict, List

import PyPDF2
try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from config import CHUNK_OVERLAP, CHUNK_SIZE, PDF_PATH


class DocumentLoader:
    """文档加载器。"""

    def __init__(self, pdf_path: str = PDF_PATH):
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
                    print(f"✓ 已加载第 {page_num + 1}/{total_pages} 页")
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
                print("使用 pdfplumber 加载 PDF...")
                with pdfplumber.open(self.pdf_path) as pdf:
                    total_pages = len(pdf.pages)
                    for page_num, page in enumerate(pdf.pages):
                        text = page.extract_text()
                        if text:
                            texts.append(text)
                            metadata.append({"page": page_num + 1, "total_pages": total_pages})
                            print(f"✓ 已加载第 {page_num + 1}/{total_pages} 页")

                self.documents = [{"text": text, "metadata": meta} for text, meta in zip(texts, metadata)]
                print(f"\n✓ 成功加载 PDF，共 {len(texts)} 页")
                return texts
            except Exception as exc:
                print(f"⚠️  pdfplumber 加载失败: {exc}，尝试 PyPDF2...")
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

        print(f"正在分块 {len(documents)} 个文档...")

        total_docs = len(documents)
        for doc_idx, doc in enumerate(documents):
            if (doc_idx + 1) % max(1, total_docs // 10) == 0:
                print(f"  进度: {doc_idx + 1}/{total_docs} 个文档")

            doc_text = doc.get("text", "")
            if not doc_text:
                continue

            chunks = self.chunk_text(doc_text, doc["metadata"].get("page"))
            for chunk in chunks:
                chunk["chunk_id"] = chunk_id
                chunk["metadata"] = doc["metadata"]
                all_chunks.append(chunk)
                chunk_id += 1

            if (doc_idx + 1) % 50 == 0:
                gc.collect()

        print(f"\n✓ 分块完成，共生成 {len(all_chunks)} 个文本块")
        gc.collect()
        return all_chunks


def prepare_documents(pdf_path: str = PDF_PATH) -> List[Dict]:
    """准备文档。"""
    print("=" * 50)
    print("开始处理文档...")
    print("=" * 50)

    print("\n[1/2] 加载PDF文件...")
    loader = DocumentLoader(pdf_path)
    loader.load_pdf()
    documents = loader.get_documents()

    print("\n[2/2] 切分文本块...")
    chunker = TextChunker()
    chunks = chunker.chunk_documents(documents)

    print("\n" + "=" * 50)
    print("✓ 文档处理完成!")
    print("=" * 50)

    return chunks


if __name__ == "__main__":
    try:
        chunks = prepare_documents()
        if chunks:
            print("\n--- 第一个文本块样本 ---")
            sample = chunks[0]
            print(f"块ID: {sample['chunk_id']}")
            print(f"页码: {sample['page']}")
            print(f"内容预览: {sample['content'][:100]}...")
    except FileNotFoundError as exc:
        print(f"错误: {exc}")
        print("请确保将PDF文件放在 ./data/ 目录中")
