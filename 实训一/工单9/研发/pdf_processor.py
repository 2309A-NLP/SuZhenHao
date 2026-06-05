"""
PDF文档处理模块
- PDF文本提取
- 文本分块
- 向量化（Embedding）
- FAISS向量库存储
"""

import os
import torch
import pdfplumber
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings
from config import (
    CHUNK_SIZE, CHUNK_OVERLAP,
    EMBEDDING_MODEL_NAME, EMBEDDING_MODEL_PATH,
    VECTOR_STORE_DIR, UPLOAD_DIR
)


class PDFProcessor:
    def __init__(self):
        """初始化Embedding模型（自动检测GPU）"""
        model_path = EMBEDDING_MODEL_PATH or EMBEDDING_MODEL_NAME
        # 自动检测GPU
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        self.embeddings = HuggingFaceEmbeddings(
            model_name=model_path,
            model_kwargs={'device': device},
            encode_kwargs={
                'normalize_embeddings': True,
                'batch_size': 64,  # 批量编码，大幅提升速度
            }
        )
        print(f"[Embedding] 使用设备: {device}")
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
            length_function=len
        )
        self.vector_store = None
        self.all_chunks = []  # 保存所有chunk，供知识图谱使用

    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """从PDF文件中提取文本"""
        full_text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n\n"
        return full_text

    def split_text(self, text: str) -> list:
        """将文本分块"""
        chunks = self.text_splitter.split_text(text)
        return chunks

    def build_vector_store(self, chunks: list) -> FAISS:
        """将文本块向量化并存入FAISS"""
        self.vector_store = FAISS.from_texts(chunks, self.embeddings)
        return self.vector_store

    def save_vector_store(self):
        """保存向量库到本地"""
        if self.vector_store:
            os.makedirs(VECTOR_STORE_DIR, exist_ok=True)
            self.vector_store.save_local(VECTOR_STORE_DIR)

    def load_vector_store(self) -> FAISS:
        """加载本地向量库"""
        if os.path.exists(VECTOR_STORE_DIR):
            self.vector_store = FAISS.load_local(
                VECTOR_STORE_DIR,
                self.embeddings,
                allow_dangerous_deserialization=True
            )
            return self.vector_store
        return None

    def process_pdf(self, pdf_path: str) -> dict:
        """
        完整的PDF处理流程
        返回：处理结果统计信息
        """
        # 1. 提取文本
        raw_text = self.extract_text_from_pdf(pdf_path)
        if not raw_text.strip():
            return {"error": "PDF中未提取到文本内容"}

        # 2. 分块
        chunks = self.split_text(raw_text)
        self.all_chunks = chunks

        # 3. 向量化并存储
        self.build_vector_store(chunks)

        # 4. 保存
        self.save_vector_store()

        return {
            "total_chars": len(raw_text),
            "total_chunks": len(chunks),
            "sample_chunks": chunks[:2]  # 预览前2个chunk
        }

    def search(self, query: str, top_k: int = 4) -> list:
        """相似度检索"""
        if not self.vector_store:
            self.load_vector_store()
        if not self.vector_store:
            return []

        results = self.vector_store.similarity_search_with_score(query, k=top_k)
        return results
