"""
向量嵌入和检索模块 - 支持 FAISS 优先、纯 Python 兜底
"""
import gc
import os
import pickle
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:
    SentenceTransformer = None

from config import EMBEDDINGS_MODEL, FAISS_INDEX_PATH, SIMILARITY_THRESHOLD, TOP_K


class EmbeddingManager:
    """文本向量化管理。"""

    def __init__(self, model_name: str = EMBEDDINGS_MODEL):
        self.model_name = model_name
        self.model = None
        self.texts: List[str] = []
        self.embeddings: Optional[np.ndarray] = None

        if SentenceTransformer is not None:
            try:
                print(f"加载嵌入模型: {model_name}")
                self.model = SentenceTransformer(model_name, local_files_only=True)
            except Exception as exc:
                print(f"⚠️  嵌入模型加载失败，切换到本地兜底模式: {exc}")

    @property
    def available(self) -> bool:
        return self.model is not None

    def _fallback_encode(self, texts: List[str]) -> np.ndarray:
        vectors = []
        for text in texts:
            vec = np.zeros(256, dtype=np.float32)
            for token in self._tokenize(text):
                idx = hash(token) % vec.shape[0]
                vec[idx] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            vectors.append(vec)
        return np.vstack(vectors) if vectors else np.empty((0, 256), dtype=np.float32)

    def _tokenize(self, text: str) -> List[str]:
        import re

        tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]+", text.lower())
        return tokens or [text[:8]]

    def embed_texts(self, chunks: List[Dict]) -> np.ndarray:
        print(f"正在嵌入 {len(chunks)} 个文本块...")
        texts = [chunk["content"] for chunk in chunks]
        self.texts = texts

        if not texts:
            self.embeddings = np.empty((0, 0), dtype=np.float32)
            return self.embeddings

        if self.model is None:
            print("⚠️  未安装 sentence-transformers，使用本地兜底向量化")
            self.embeddings = self._fallback_encode(texts)
            return self.embeddings

        batch_size = 256
        all_embeddings = []
        total_batches = (len(texts) + batch_size - 1) // batch_size

        for batch_idx in range(0, len(texts), batch_size):
            end_idx = min(batch_idx + batch_size, len(texts))
            batch_texts = texts[batch_idx:end_idx]
            current_batch = (batch_idx // batch_size) + 1

            if current_batch % 5 == 0 or current_batch == total_batches:
                print(f"  处理批次: {current_batch}/{total_batches}")

            try:
                batch_embeddings = self.model.encode(
                    batch_texts,
                    show_progress_bar=False,
                    convert_to_numpy=True,
                )
                all_embeddings.append(batch_embeddings)
            except Exception as exc:
                print(f"警告：批次 {current_batch} 处理出错: {exc}")
                continue

            if current_batch % 10 == 0:
                gc.collect()

        embeddings = np.vstack(all_embeddings) if all_embeddings else np.empty((0, 0), dtype=np.float32)
        self.embeddings = embeddings
        print(f"✓ 嵌入完成，维度: {embeddings.shape if embeddings.size > 0 else 0}")
        gc.collect()
        return embeddings

    def get_embedding(self, text: str) -> np.ndarray:
        if self.model is None:
            return self._fallback_encode([text])[0]
        return self.model.encode(text, convert_to_numpy=True)


class FAISSRetriever:
    """FAISS 检索器。"""

    def __init__(self):
        self.index = None
        self.chunks = []
        self.embeddings = None

    @property
    def available(self) -> bool:
        return faiss is not None

    def build_index(self, chunks: List[Dict], embeddings: np.ndarray):
        if not self.available:
            raise ImportError("请安装 faiss-cpu")
        if embeddings is None or embeddings.size == 0:
            raise ValueError("嵌入向量为空，无法构建索引")
        if len(embeddings.shape) != 2:
            raise ValueError(f"嵌入向量维度异常: {embeddings.shape}")

        self.chunks = chunks
        self.embeddings = embeddings

        dimension = embeddings.shape[1]
        vectors = embeddings.astype(np.float32).copy()
        faiss.normalize_L2(vectors)
        self.index = faiss.IndexFlatIP(dimension)
        self.index.add(vectors)

        print(f"✓ FAISS 索引构建完成，包含 {len(chunks)} 个文本块")
        self._save_index()

    def _save_index(self):
        os.makedirs(FAISS_INDEX_PATH, exist_ok=True)
        if self.index is not None:
            faiss.write_index(self.index, os.path.join(FAISS_INDEX_PATH, "faiss.index"))
        with open(os.path.join(FAISS_INDEX_PATH, "chunks.pkl"), "wb") as f:
            pickle.dump(self.chunks, f)
        print(f"✓ 索引已保存到 {FAISS_INDEX_PATH}")

    def load_index(self):
        if not self.available:
            raise ImportError("请安装 faiss-cpu")

        index_path = os.path.join(FAISS_INDEX_PATH, "faiss.index")
        chunks_path = os.path.join(FAISS_INDEX_PATH, "chunks.pkl")

        if not os.path.exists(index_path):
            raise FileNotFoundError(f"索引文件不存在: {index_path}")

        print("加载 FAISS 索引...")
        self.index = faiss.read_index(index_path)
        with open(chunks_path, "rb") as f:
            self.chunks = pickle.load(f)
        print(f"✓ 索引加载完成，包含 {len(self.chunks)} 个文本块")

    def retrieve(self, query_embedding: np.ndarray, k: int = TOP_K, threshold: float = SIMILARITY_THRESHOLD) -> List[Dict]:
        if self.index is None:
            raise ValueError("索引尚未初始化")

        query_vec = np.array([query_embedding], dtype=np.float32).copy()
        faiss.normalize_L2(query_vec)
        scores, indices = self.index.search(query_vec, k)

        results = []
        for idx, score in zip(indices[0], scores[0]):
            if idx < len(self.chunks):
                chunk = self.chunks[idx]
                similarity = float(score)
                if similarity > threshold:
                    results.append(
                        {
                            "chunk_id": chunk.get("chunk_id"),
                            "content": chunk.get("content"),
                            "page": chunk.get("page"),
                            "similarity": similarity,
                            "distance": float(1 - similarity),
                        }
                    )
        return results


class LocalRetriever:
    """不依赖 FAISS 的轻量检索器。"""

    def __init__(self):
        self.chunks: List[Dict] = []
        self.embedding_manager = EmbeddingManager()
        self.embeddings: Optional[np.ndarray] = None

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        denom = float(np.linalg.norm(a) * np.linalg.norm(b))
        if denom == 0:
            return 0.0
        return float(np.dot(a, b) / denom)

    def build_index(self, chunks: List[Dict], embeddings: np.ndarray):
        self.chunks = chunks
        self.embeddings = embeddings
        os.makedirs(FAISS_INDEX_PATH, exist_ok=True)
        with open(os.path.join(FAISS_INDEX_PATH, "chunks.pkl"), "wb") as f:
            pickle.dump(self.chunks, f)
        if embeddings is not None and embeddings.size > 0:
            np.save(os.path.join(FAISS_INDEX_PATH, "embeddings.npy"), embeddings)

    def load_index(self):
        chunks_path = os.path.join(FAISS_INDEX_PATH, "chunks.pkl")
        embeddings_path = os.path.join(FAISS_INDEX_PATH, "embeddings.npy")
        if not os.path.exists(chunks_path):
            raise FileNotFoundError(f"索引文件不存在: {chunks_path}")
        with open(chunks_path, "rb") as f:
            self.chunks = pickle.load(f)
        if os.path.exists(embeddings_path):
            self.embeddings = np.load(embeddings_path)

    def retrieve(self, query_embedding: np.ndarray, k: int = TOP_K, threshold: float = SIMILARITY_THRESHOLD) -> List[Dict]:
        if self.embeddings is None or len(self.chunks) == 0:
            return []

        scores = []
        for idx, emb in enumerate(self.embeddings):
            sim = self._cosine_similarity(query_embedding, emb)
            scores.append((idx, sim))

        scores.sort(key=lambda item: item[1], reverse=True)

        results = []
        for idx, similarity in scores[:k]:
            if similarity > threshold:
                chunk = self.chunks[idx]
                results.append(
                    {
                        "chunk_id": chunk.get("chunk_id"),
                        "content": chunk.get("content"),
                        "page": chunk.get("page"),
                        "similarity": float(similarity),
                        "distance": float(1 - similarity),
                    }
                )
        return results


class RAGRetriever:
    """统一检索入口。"""

    def __init__(self):
        self.embedding_manager = None
        self.retriever = None
        self.backend = "faiss" if faiss is not None else "local"

    def initialize(self, chunks: List[Dict]):
        print("\n" + "=" * 50)
        print("初始化 RAG 检索系统...")
        print("=" * 50)

        self.embedding_manager = EmbeddingManager()
        embeddings = self.embedding_manager.embed_texts(chunks)

        if faiss is not None:
            self.retriever = FAISSRetriever()
            self.retriever.build_index(chunks, embeddings)
            self.backend = "faiss"
        else:
            self.retriever = LocalRetriever()
            self.retriever.build_index(chunks, embeddings)
            self.backend = "local"
            print("⚠️  未安装 faiss-cpu，已切换到本地检索模式")

        print("\n✓ RAG 检索系统初始化完成")

    def retrieve(self, query: str, k: int = TOP_K) -> List[Dict]:
        if self.embedding_manager is None or self.retriever is None:
            raise ValueError("检索系统未初始化")

        query_embedding = self.embedding_manager.get_embedding(query)
        threshold = getattr(self, '_fallback_threshold', SIMILARITY_THRESHOLD)
        try:
            return self.retriever.retrieve(query_embedding, k, threshold=threshold)
        except Exception as exc:
            # 如果 FAISS 检索失败（如维度不匹配），切换到本地检索
            if isinstance(self.retriever, FAISSRetriever):
                print(f"⚠️  FAISS 检索失败，切换到本地检索: {exc}")
                local = LocalRetriever()
                local.chunks = self.retriever.chunks
                local.embeddings = self.embedding_manager.embed_texts(local.chunks)
                self.retriever = local
                self.backend = "local"
                return self.retriever.retrieve(query_embedding, k, threshold=threshold)
            raise

    def load_from_index(self):
        self.embedding_manager = EmbeddingManager()

        if faiss is not None and self.embedding_manager.available:
            self.retriever = FAISSRetriever()
            try:
                self.retriever.load_index()
                self.backend = "faiss"
            except Exception:
                self.retriever = LocalRetriever()
                self.retriever.load_index()
                self.backend = "local"
        else:
            self.retriever = LocalRetriever()
            self.retriever.load_index()
            self.backend = "local"

        if isinstance(self.retriever, LocalRetriever) and self.retriever.embeddings is None and self.retriever.chunks:
            self.retriever.embeddings = self.embedding_manager.embed_texts(self.retriever.chunks)

        # 兜底模式下降低相似度阈值，确保能返回结果
        if not self.embedding_manager.available:
            print("📌 本地兜底模式：已自动降低相似度阈值")
            self._fallback_threshold = 0.01
        else:
            self._fallback_threshold = SIMILARITY_THRESHOLD


if __name__ == "__main__":
    print("RAG 检索模块测试")
