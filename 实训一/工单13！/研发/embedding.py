"""
向量嵌入和检索模块 - 支持 FAISS、BM25、混合检索
支持三种检索模式：vector / bm25 / hybrid
"""
import gc
import os
import pickle
import re
from typing import Dict, List, Optional, Tuple

import numpy as np

try:
    import faiss
except ImportError:
    faiss = None

try:
    from pymilvus import (
        connections, Collection, CollectionSchema, FieldSchema, DataType,
        utility,
    )
except ImportError:
    Collection = None

try:
    from sentence_transformers import SentenceTransformer, CrossEncoder
except ImportError:
    SentenceTransformer = None
    CrossEncoder = None

try:
    from rank_bm25 import BM25Okapi
except ImportError:
    BM25Okapi = None

try:
    import jieba
except ImportError:
    jieba = None

from config import (
    EMBEDDINGS_MODEL,
    FAISS_INDEX_PATH,
    SIMILARITY_THRESHOLD,
    TOP_K,
    BM25_TOP_K,
    RERANK_TOP_K,
    RERANKER_MODEL,
    RETRIEVAL_MODE,
    LIGHTRAG_GRAPH_PATH,
    MILVUS_HOST,
    MILVUS_PORT,
    MILVUS_COLLECTION_NAME,
    MILVUS_INDEX_TYPE,
    MILVUS_METRIC_TYPE,
    MILVUS_NLIST,
    MEMORY_COLLECTION_NAME,
    MEMORY_TOP_K,
    MEMORY_SIMILARITY_THRESHOLD,
)


# ═══════════════════════════════════════════════════════════
# 文本分词工具
# ═══════════════════════════════════════════════════════════

def tokenize_chinese(text: str) -> List[str]:
    """中文分词：优先使用 jieba，回退到简单字符切分。"""
    if jieba is not None:
        return list(jieba.cut(text))
    # 简单兜底：按字符和英文单词切分
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9_]+", text.lower())
    return tokens or [text[:8]]


def tokenize_for_bm25(text: str) -> List[str]:
    """为 BM25 分词：去除停用词，保留有意义的词。"""
    tokens = tokenize_chinese(text.lower())
    stopwords = {"的", "了", "是", "在", "和", "有", "为", "等", "不", "对", "与",
                 "也", "就", "都", "而", "及", "或", "这", "那", "中", "上", "下",
                 "一个", "一些", "一", "the", "a", "an", "is", "are", "was", "were",
                 "in", "on", "at", "to", "for", "of", "with", "and", "or", "but"}
    return [t for t in tokens if len(t) > 1 and t not in stopwords]


# ═══════════════════════════════════════════════════════════
# 向量嵌入管理
# ═══════════════════════════════════════════════════════════

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
                print(f"✓ 嵌入模型加载成功")
            except Exception as exc:
                print(f"⚠️  嵌入模型加载失败，切换到本地兜底模式: {exc}")

    @property
    def available(self) -> bool:
        return self.model is not None

    def _fallback_encode(self, texts: List[str]) -> np.ndarray:
        vectors = []
        for text in texts:
            vec = np.zeros(256, dtype=np.float32)
            for token in tokenize_chinese(text):
                idx = hash(token) % vec.shape[0]
                vec[idx] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            vectors.append(vec)
        return np.vstack(vectors) if vectors else np.empty((0, 256), dtype=np.float32)

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

        # 尝试从 Redis 缓存获取
        cached_embeddings = {}
        uncached_texts = []
        uncached_indices = []
        try:
            from redis_cache import get_embedding_cache_batch, set_embedding_cache_batch
            cached = get_embedding_cache_batch(texts)
            for i, text in enumerate(texts):
                if text in cached:
                    cached_embeddings[i] = cached[text]
                else:
                    uncached_texts.append(text)
                    uncached_indices.append(i)
            if cached_embeddings:
                print(f"  [Embedding缓存] 命中 {len(cached_embeddings)}/{len(texts)} 条")
        except Exception:
            uncached_texts = texts
            uncached_indices = list(range(len(texts)))

        # 计算未缓存的 embedding
        new_embeddings = {}
        if uncached_texts:
            batch_size = 256
            all_embeddings = []
            total_batches = (len(uncached_texts) + batch_size - 1) // batch_size

            for batch_idx in range(0, len(uncached_texts), batch_size):
                end_idx = min(batch_idx + batch_size, len(uncached_texts))
                batch_texts = uncached_texts[batch_idx:end_idx]
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

            if all_embeddings:
                computed = np.vstack(all_embeddings)
                for i, idx in enumerate(uncached_indices):
                    new_embeddings[idx] = computed[i].tolist()

            # 写入缓存
            try:
                if new_embeddings:
                    set_embedding_cache_batch(
                        uncached_texts,
                        [new_embeddings[idx] for idx in uncached_indices]
                    )
                    print(f"  [Embedding缓存] 写入 {len(new_embeddings)} 条")
            except Exception:
                pass

        # 合并缓存和新计算的 embedding
        all_result = []
        for i in range(len(texts)):
            if i in cached_embeddings:
                all_result.append(cached_embeddings[i])
            elif i in new_embeddings:
                all_result.append(new_embeddings[i])

        embeddings = np.array(all_result, dtype=np.float32) if all_result else np.empty((0, 0), dtype=np.float32)
        self.embeddings = embeddings
        print(f"✓ 嵌入完成，维度: {embeddings.shape if embeddings.size > 0 else 0}")
        gc.collect()
        return embeddings

    def get_embedding(self, text: str) -> np.ndarray:
        if self.model is None:
            return self._fallback_encode([text])[0]
        return self.model.encode(text, convert_to_numpy=True)


# ═══════════════════════════════════════════════════════════
# BM25 全文检索器
# ═══════════════════════════════════════════════════════════

class BM25Retriever:
    """基于 BM25 的全文检索器。"""

    def __init__(self):
        self.bm25 = None
        self.chunks: List[Dict] = []
        self.tokenized_corpus: List[List[str]] = []

    def build_index(self, chunks: List[Dict]):
        """构建 BM25 索引。"""
        if BM25Okapi is None:
            raise ImportError("请安装 rank-bm25: pip install rank-bm25")

        self.chunks = chunks
        print(f"正在构建 BM25 索引（{len(chunks)} 个文本块）...")

        self.tokenized_corpus = [tokenize_for_bm25(chunk["content"]) for chunk in chunks]
        self.bm25 = BM25Okapi(self.tokenized_corpus)

        # 保存索引
        self._save_index()
        print(f"✓ BM25 索引构建完成")

    def _save_index(self):
        """保存 BM25 索引到磁盘。"""
        os.makedirs(FAISS_INDEX_PATH, exist_ok=True)
        bm25_path = os.path.join(FAISS_INDEX_PATH, "bm25_data.pkl")
        with open(bm25_path, "wb") as f:
            pickle.dump({
                "chunks": self.chunks,
                "tokenized_corpus": self.tokenized_corpus,
            }, f)

    def load_index(self):
        """从磁盘加载 BM25 索引。"""
        bm25_path = os.path.join(FAISS_INDEX_PATH, "bm25_data.pkl")
        if not os.path.exists(bm25_path):
            raise FileNotFoundError(f"BM25 索引文件不存在: {bm25_path}")

        print("加载 BM25 索引...")
        with open(bm25_path, "rb") as f:
            data = pickle.load(f)
        self.chunks = data["chunks"]
        self.tokenized_corpus = data["tokenized_corpus"]
        self.bm25 = BM25Okapi(self.tokenized_corpus)
        print(f"✓ BM25 索引加载完成，包含 {len(self.chunks)} 个文本块")

    def retrieve(self, query: str, k: int = BM25_TOP_K, threshold: float = 0) -> List[Dict]:
        """BM25 检索，返回 Top-K 结果。"""
        if self.bm25 is None:
            raise ValueError("BM25 索引尚未初始化")

        query_tokens = tokenize_for_bm25(query)
        scores = self.bm25.get_scores(query_tokens)

        # 获取 Top-K 索引
        top_indices = np.argsort(scores)[::-1][:k]

        results = []
        for idx in top_indices:
            score = float(scores[idx])
            if score > threshold and idx < len(self.chunks):
                chunk = self.chunks[idx]
                results.append({
                    "chunk_id": chunk.get("chunk_id"),
                    "content": chunk.get("content"),
                    "page": chunk.get("page"),
                    "source": chunk.get("source", "unknown"),
                    "similarity": score,
                    "distance": 0.0,
                    "retrieval_method": "bm25",
                })
        return results


# ═══════════════════════════════════════════════════════════
# Reranker 重排序器
# ═══════════════════════════════════════════════════════════

class Reranker:
    """基于 CrossEncoder 的重排序器。"""

    def __init__(self, model_name: str = RERANKER_MODEL):
        self.model_name = model_name
        self.model = None

        if CrossEncoder is not None:
            try:
                print(f"加载重排模型: {model_name}")
                self.model = CrossEncoder(model_name, max_length=512)
                print(f"✓ 重排模型加载成功")
            except Exception as exc:
                print(f"⚠️  重排模型加载失败: {exc}")

    @property
    def available(self) -> bool:
        return self.model is not None

    def rerank(self, query: str, results: List[Dict], top_k: int = RERANK_TOP_K) -> List[Dict]:
        """对检索结果进行重排序。"""
        if not results:
            return []

        if not self.available:
            print("⚠️  重排模型不可用，返回原始排序")
            return results[:top_k]

        # 构建 query-document 对
        pairs = [(query, doc["content"]) for doc in results]

        # CrossEncoder 打分
        scores = self.model.predict(pairs)

        # 将分数附加到结果上并重新排序
        for i, score in enumerate(scores):
            results[i]["rerank_score"] = float(score)

        results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)

        return results[:top_k]


# ═══════════════════════════════════════════════════════════
# FAISS 向量检索器
# ═══════════════════════════════════════════════════════════

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
                            "source": chunk.get("source", "unknown"),
                            "similarity": similarity,
                            "distance": float(1 - similarity),
                            "retrieval_method": "vector",
                        }
                    )
        return results


# ═══════════════════════════════════════════════════════════
# Milvus 向量检索器
# ═══════════════════════════════════════════════════════════

class MilvusRetriever:
    """Milvus 向量检索器。"""

    def __init__(self):
        self.collection = None
        self.chunks: List[Dict] = []
        self.connected = False

    @property
    def available(self) -> bool:
        return Collection is not None

    def _connect(self):
        """连接 Milvus 服务。"""
        if not self.connected:
            try:
                connections.connect(alias="default", host=MILVUS_HOST, port=MILVUS_PORT)
                self.connected = True
                print(f"✓ 已连接 Milvus ({MILVUS_HOST}:{MILVUS_PORT})")
            except Exception as exc:
                raise ConnectionError(f"Milvus 连接失败: {exc}")

    def _create_collection(self, dimension: int):
        """创建 Milvus 集合。"""
        # 如果已存在则先删除
        if utility.has_collection(MILVUS_COLLECTION_NAME):
            utility.drop_collection(MILVUS_COLLECTION_NAME)
            print(f"  已删除旧集合: {MILVUS_COLLECTION_NAME}")

        # 定义字段
        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="chunk_id", dtype=DataType.VARCHAR, max_length=64),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="page", dtype=DataType.INT64),
            FieldSchema(name="source", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dimension),
        ]

        schema = CollectionSchema(fields=fields, description="RAG document chunks")
        self.collection = Collection(name=MILVUS_COLLECTION_NAME, schema=schema)
        print(f"✓ 创建 Milvus 集合: {MILVUS_COLLECTION_NAME}（维度: {dimension}）")

    def build_index(self, chunks: List[Dict], embeddings: np.ndarray):
        """构建 Milvus 索引。"""
        if not self.available:
            raise ImportError("请安装 pymilvus: pip install pymilvus")
        if embeddings is None or embeddings.size == 0:
            raise ValueError("嵌入向量为空，无法构建索引")

        self._connect()
        self.chunks = chunks

        dimension = embeddings.shape[1]
        self._create_collection(dimension)

        # 准备插入数据
        chunk_ids = [str(chunk.get("chunk_id", i)) for i, chunk in enumerate(chunks)]
        contents = [str(chunk.get("content", ""))[:8000] for chunk in chunks]
        pages = [int(chunk.get("page", 0)) for chunk in chunks]
        sources = [str(chunk.get("source", "unknown"))[:500] for chunk in chunks]
        vectors = embeddings.astype(np.float32).tolist()

        # 批量插入
        batch_size = 1000
        total_inserted = 0
        for i in range(0, len(chunks), batch_size):
            end = min(i + batch_size, len(chunks))
            self.collection.insert([
                chunk_ids[i:end],
                contents[i:end],
                pages[i:end],
                sources[i:end],
                vectors[i:end],
            ])
            total_inserted += end - i

        self.collection.flush()
        print(f"  已插入 {total_inserted} 条数据")

        # 构建索引
        index_params = {
            "metric_type": MILVUS_METRIC_TYPE,
            "index_type": MILVUS_INDEX_TYPE,
            "params": {"nlist": MILVUS_NLIST},
        }
        self.collection.create_index(field_name="embedding", index_params=index_params)
        print(f"✓ Milvus 索引构建完成（{MILVUS_INDEX_TYPE}, {MILVUS_METRIC_TYPE}）")

        # 加载到内存
        self.collection.load()

    def load_index(self):
        """连接并加载已有的 Milvus 集合。"""
        if not self.available:
            raise ImportError("请安装 pymilvus: pip install pymilvus")

        self._connect()

        if not utility.has_collection(MILVUS_COLLECTION_NAME):
            raise FileNotFoundError(f"Milvus 集合不存在: {MILVUS_COLLECTION_NAME}")

        print(f"加载 Milvus 集合: {MILVUS_COLLECTION_NAME}...")
        self.collection = Collection(name=MILVUS_COLLECTION_NAME)
        self.collection.load()

        # 从 Milvus 中读取 chunks 元数据
        count = self.collection.num_entities
        print(f"✓ Milvus 集合加载完成，包含 {count} 条记录")

        # 查询所有 chunk 元数据（用于返回检索结果时附带内容）
        try:
            results = self.collection.query(
                expr="chunk_id != ''",
                output_fields=["chunk_id", "content", "page", "source"],
                limit=count,
            )
            self.chunks = [
                {
                    "chunk_id": r["chunk_id"],
                    "content": r["content"],
                    "page": r["page"],
                    "source": r["source"],
                }
                for r in results
            ]
        except Exception as exc:
            print(f"⚠️  读取 chunks 元数据失败: {exc}")
            self.chunks = []

    def retrieve(self, query_embedding: np.ndarray, k: int = TOP_K, threshold: float = SIMILARITY_THRESHOLD) -> List[Dict]:
        """Milvus 向量检索。"""
        if self.collection is None:
            raise ValueError("Milvus 集合未初始化")

        query_vec = query_embedding.astype(np.float32).tolist()

        search_params = {
            "metric_type": MILVUS_METRIC_TYPE,
            "params": {"nprobe": min(16, MILVUS_NLIST)},
        }

        results = self.collection.search(
            data=[query_vec],
            anns_field="embedding",
            param=search_params,
            limit=k,
            output_fields=["chunk_id", "content", "page", "source"],
        )

        retrieved = []
        for hit in results[0]:
            similarity = float(hit.score)
            if MILVUS_METRIC_TYPE == "L2":
                # L2 距离转相似度
                similarity = 1.0 / (1.0 + similarity)

            if similarity > threshold:
                entity = hit.entity
                retrieved.append({
                    "chunk_id": entity.get("chunk_id"),
                    "content": entity.get("content"),
                    "page": entity.get("page"),
                    "source": entity.get("source", "unknown"),
                    "similarity": similarity,
                    "distance": float(1 - similarity),
                    "retrieval_method": "vector",
                })
        return retrieved


# ═══════════════════════════════════════════════════════════
# 对话记忆管理（Milvus 长期记忆）
# ═══════════════════════════════════════════════════════════

class ConversationMemory:
    """基于 Milvus 的对话长期记忆。独立集合，不与文档知识库混合。"""

    def __init__(self):
        self.collection = None
        self.embedding_manager = None
        self.connected = False

    @property
    def available(self) -> bool:
        return Collection is not None

    def _connect(self):
        if not self.connected:
            try:
                connections.connect(alias="memory", host=MILVUS_HOST, port=MILVUS_PORT)
                self.connected = True
            except Exception as exc:
                raise ConnectionError(f"Milvus 连接失败: {exc}")

    def initialize(self, embedding_manager: EmbeddingManager):
        """初始化对话记忆集合（如已存在则直接加载）。"""
        if not self.available:
            print("⚠️  pymilvus 未安装，对话记忆不可用")
            return

        self._connect()
        self.embedding_manager = embedding_manager

        if utility.has_collection(MEMORY_COLLECTION_NAME, using="memory"):
            self.collection = Collection(name=MEMORY_COLLECTION_NAME, using="memory")
            self.collection.load()
            count = self.collection.num_entities
            print(f"✓ 对话记忆集合已加载，包含 {count} 条记录")
        else:
            self._create_collection()

    def _create_collection(self):
        """创建对话记忆集合。"""
        # 获取 embedding 维度
        dim = 768  # 默认 m3e-base 维度
        if self.embedding_manager and self.embedding_manager.available:
            try:
                test_vec = self.embedding_manager.get_embedding("测试")
                dim = len(test_vec)
            except Exception:
                pass

        fields = [
            FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
            FieldSchema(name="content", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="timestamp", dtype=DataType.VARCHAR, max_length=32),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=dim),
        ]
        schema = CollectionSchema(fields=fields, description="对话长期记忆")
        self.collection = Collection(name=MEMORY_COLLECTION_NAME, schema=schema, using="memory")
        # 构建索引
        index_params = {
            "metric_type": MILVUS_METRIC_TYPE,
            "index_type": MILVUS_INDEX_TYPE,
            "params": {"nlist": MILVUS_NLIST},
        }
        self.collection.create_index(field_name="embedding", index_params=index_params)
        self.collection.load()
        print(f"✓ 对话记忆集合已创建: {MEMORY_COLLECTION_NAME}")

    def add(self, query: str, answer: str):
        """存储一条问答记录。"""
        if self.collection is None or self.embedding_manager is None:
            return

        from datetime import datetime
        content = f"用户问：{query}\n助手答：{answer}"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        try:
            embedding = self.embedding_manager.get_embedding(content)
            self.collection.insert([
                [content],
                [timestamp],
                [embedding.astype(np.float32).tolist()],
            ])
            self.collection.flush()
            print(f"  [记忆] 已存储对话记录")
        except Exception as exc:
            print(f"⚠️  对话记忆存储失败: {exc}")

    def search(self, query: str, top_k: int = MEMORY_TOP_K) -> List[Dict]:
        """检索相关的对话记忆。"""
        if self.collection is None or self.embedding_manager is None:
            return []

        if self.collection.num_entities == 0:
            return []

        try:
            query_vec = self.embedding_manager.get_embedding(query).astype(np.float32).tolist()
            search_params = {
                "metric_type": MILVUS_METRIC_TYPE,
                "params": {"nprobe": min(16, MILVUS_NLIST)},
            }
            results = self.collection.search(
                data=[query_vec],
                anns_field="embedding",
                param=search_params,
                limit=top_k,
                output_fields=["content", "timestamp"],
            )

            memories = []
            for hit in results[0]:
                similarity = float(hit.score)
                if MILVUS_METRIC_TYPE == "L2":
                    similarity = 1.0 / (1.0 + similarity)
                if similarity >= MEMORY_SIMILARITY_THRESHOLD:
                    memories.append({
                        "content": hit.entity.get("content"),
                        "timestamp": hit.entity.get("timestamp"),
                        "similarity": similarity,
                    })
            return memories
        except Exception as exc:
            print(f"⚠️  对话记忆检索失败: {exc}")
            return []

    def clear(self):
        """清空对话记忆。"""
        if self.collection is None:
            return
        try:
            if utility.has_collection(MEMORY_COLLECTION_NAME, using="memory"):
                utility.drop_collection(MEMORY_COLLECTION_NAME, using="memory")
                print(f"[清理] 已清空对话记忆: {MEMORY_COLLECTION_NAME}")
            self._create_collection()
        except Exception as exc:
            print(f"⚠️  清空对话记忆失败: {exc}")


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
                        "source": chunk.get("source", "unknown"),
                        "similarity": float(similarity),
                        "distance": float(1 - similarity),
                        "retrieval_method": "vector",
                    }
                )
        return results


# ═══════════════════════════════════════════════════════════
# 混合检索器
# ═══════════════════════════════════════════════════════════

class HybridRetriever:
    """混合检索器：BM25 + 向量检索 → RRF 融合 → Reranker 精排。"""

    def __init__(self):
        self.bm25_retriever = BM25Retriever()
        self.vector_retriever = None  # FAISSRetriever 或 LocalRetriever
        self.embedding_manager = None
        self.reranker = Reranker()
        self.chunks: List[Dict] = []

    def initialize(self, chunks: List[Dict]):
        """构建 BM25 + 向量双重索引。"""
        self.chunks = chunks

        # 构建 BM25 索引
        self.bm25_retriever.build_index(chunks)

        # 构建向量索引（优先 Milvus，回退 FAISS）
        self.embedding_manager = EmbeddingManager()
        embeddings = self.embedding_manager.embed_texts(chunks)

        if Collection is not None:
            try:
                self.vector_retriever = MilvusRetriever()
                self.vector_retriever.build_index(chunks, embeddings)
            except Exception as exc:
                print(f"⚠️  Milvus 不可用，回退到 FAISS: {exc}")
                if faiss is not None:
                    self.vector_retriever = FAISSRetriever()
                    self.vector_retriever.build_index(chunks, embeddings)
                else:
                    self.vector_retriever = LocalRetriever()
                    self.vector_retriever.build_index(chunks, embeddings)
        elif faiss is not None:
            self.vector_retriever = FAISSRetriever()
            self.vector_retriever.build_index(chunks, embeddings)
        else:
            self.vector_retriever = LocalRetriever()
            self.vector_retriever.build_index(chunks, embeddings)
            print("⚠️  未安装 faiss-cpu，向量检索使用本地模式")

    def load_from_index(self):
        """从磁盘加载已有索引。"""
        # 加载 BM25
        self.bm25_retriever.load_index()

        # 加载向量索引（优先 Milvus，回退 FAISS）
        self.embedding_manager = EmbeddingManager()
        milvus_loaded = False

        if Collection is not None:
            try:
                self.vector_retriever = MilvusRetriever()
                self.vector_retriever.load_index()
                milvus_loaded = True
            except Exception as exc:
                print(f"⚠️  Milvus 加载失败，回退到 FAISS: {exc}")

        if not milvus_loaded:
            if faiss is not None:
                self.vector_retriever = FAISSRetriever()
                try:
                    self.vector_retriever.load_index()
                except Exception:
                    self.vector_retriever = LocalRetriever()
                    self.vector_retriever.load_index()
            else:
                self.vector_retriever = LocalRetriever()
                self.vector_retriever.load_index()

            if isinstance(self.vector_retriever, LocalRetriever) and self.vector_retriever.embeddings is None and self.vector_retriever.chunks:
                self.vector_retriever.embeddings = self.embedding_manager.embed_texts(self.vector_retriever.chunks)

        # Milvus 模式下从集合中获取 chunks，否则从 BM25 获取
        if milvus_loaded and self.vector_retriever.chunks:
            self.chunks = self.vector_retriever.chunks
        else:
            self.chunks = self.bm25_retriever.chunks

    def _rrf_fusion(self, bm25_results: List[Dict], vector_results: List[Dict], k: int = 60) -> List[Dict]:
        """Reciprocal Rank Fusion 融合排序。"""
        doc_scores: Dict[str, float] = {}
        doc_map: Dict[str, Dict] = {}

        # BM25 结果打分
        for rank, doc in enumerate(bm25_results):
            doc_id = f"{doc.get('chunk_id', '')}_{doc.get('source', '')}_{doc.get('page', '')}"
            doc_scores[doc_id] = doc_scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
            doc_map[doc_id] = doc

        # 向量检索结果打分
        for rank, doc in enumerate(vector_results):
            doc_id = f"{doc.get('chunk_id', '')}_{doc.get('source', '')}_{doc.get('page', '')}"
            doc_scores[doc_id] = doc_scores.get(doc_id, 0) + 1.0 / (k + rank + 1)
            doc_map[doc_id] = doc

        # 按 RRF 分数排序
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)

        results = []
        for doc_id, rrf_score in sorted_docs:
            doc = doc_map[doc_id].copy()
            doc["rrf_score"] = rrf_score
            doc["retrieval_method"] = "hybrid"
            results.append(doc)

        return results

    def retrieve(self, query: str, k: int = TOP_K) -> List[Dict]:
        """混合检索：BM25 + 向量 → RRF 融合 → Reranker 精排。"""
        # 1. BM25 检索
        bm25_results = self.bm25_retriever.retrieve(query, k=BM25_TOP_K)
        print(f"  [BM25] 召回 {len(bm25_results)} 个结果")

        # 2. 向量检索
        query_embedding = self.embedding_manager.get_embedding(query)
        threshold = getattr(self, '_fallback_threshold', SIMILARITY_THRESHOLD)
        vector_results = self.vector_retriever.retrieve(query_embedding, k=BM25_TOP_K, threshold=threshold)
        print(f"  [向量] 召回 {len(vector_results)} 个结果")

        # 3. RRF 融合
        fused_results = self._rrf_fusion(bm25_results, vector_results)
        print(f"  [RRF] 融合后 {len(fused_results)} 个结果")

        # 4. Reranker 精排
        if self.reranker.available:
            final_results = self.reranker.rerank(query, fused_results, top_k=k)
            print(f"  [Reranker] 精排后 {len(final_results)} 个结果")
        else:
            final_results = fused_results[:k]
            print(f"  [无Reranker] 直接取 Top-{k}")

        return final_results


# ═══════════════════════════════════════════════════════════
# 统一检索入口
# ═══════════════════════════════════════════════════════════

class RAGRetriever:
    """统一检索入口，根据配置自动选择检索模式。"""

    def __init__(self, retrieval_mode: str = RETRIEVAL_MODE):
        self.retrieval_mode = retrieval_mode
        self.embedding_manager = None
        self.retriever = None
        self.backend = retrieval_mode

    def initialize(self, chunks: List[Dict]):
        print("\n" + "=" * 50)
        print(f"初始化检索系统（模式: {self.retrieval_mode}）...")
        print("=" * 50)

        if self.retrieval_mode == "bm25":
            self.retriever = BM25Retriever()
            self.retriever.build_index(chunks)

        elif self.retrieval_mode == "vector":
            self.embedding_manager = EmbeddingManager()
            embeddings = self.embedding_manager.embed_texts(chunks)
            if Collection is not None:
                try:
                    self.retriever = MilvusRetriever()
                    self.retriever.build_index(chunks, embeddings)
                except Exception as exc:
                    print(f"⚠️  Milvus 不可用，回退到 FAISS: {exc}")
                    if faiss is not None:
                        self.retriever = FAISSRetriever()
                        self.retriever.build_index(chunks, embeddings)
                    else:
                        self.retriever = LocalRetriever()
                        self.retriever.build_index(chunks, embeddings)
            elif faiss is not None:
                self.retriever = FAISSRetriever()
                self.retriever.build_index(chunks, embeddings)
            else:
                self.retriever = LocalRetriever()
                self.retriever.build_index(chunks, embeddings)

        elif self.retrieval_mode == "hybrid":
            self.retriever = HybridRetriever()
            self.retriever.initialize(chunks)

        elif self.retrieval_mode == "lightrag":
            from lightrag_retriever import LightRAGRetriever
            self.retriever = LightRAGRetriever()
            self.retriever.initialize(chunks)

        else:
            raise ValueError(f"不支持的检索模式: {self.retrieval_mode}，可选: vector / bm25 / hybrid / lightrag")

        print(f"\n✓ 检索系统初始化完成（模式: {self.retrieval_mode}）")

    def retrieve(self, query: str, k: int = TOP_K) -> List[Dict]:
        if self.retriever is None:
            raise ValueError("检索系统未初始化")

        print(f"[检索] 模式: {self.retrieval_mode}，查询: {query[:50]}...")

        try:
            return self.retriever.retrieve(query, k=k)
        except Exception as exc:
            # hybrid 模式下的容错：如果向量部分失败，降级为纯 BM25
            if self.retrieval_mode == "hybrid":
                print(f"⚠️  混合检索失败，降级为 BM25: {exc}")
                bm25 = self.retriever.bm25_retriever
                return bm25.retrieve(query, k=k)
            raise

    def load_from_index(self):
        if self.retrieval_mode == "bm25":
            self.retriever = BM25Retriever()
            self.retriever.load_index()

        elif self.retrieval_mode == "vector":
            self.embedding_manager = EmbeddingManager()
            milvus_loaded = False

            if Collection is not None:
                try:
                    self.retriever = MilvusRetriever()
                    self.retriever.load_index()
                    milvus_loaded = True
                except Exception as exc:
                    print(f"⚠️  Milvus 加载失败，回退到 FAISS: {exc}")

            if not milvus_loaded:
                if faiss is not None:
                    self.retriever = FAISSRetriever()
                    try:
                        self.retriever.load_index()
                    except Exception:
                        self.retriever = LocalRetriever()
                        self.retriever.load_index()
                else:
                    self.retriever = LocalRetriever()
                    self.retriever.load_index()

                if isinstance(self.retriever, LocalRetriever) and self.retriever.embeddings is None and self.retriever.chunks:
                    self.retriever.embeddings = self.embedding_manager.embed_texts(self.retriever.chunks)

            if not self.embedding_manager.available:
                self._fallback_threshold = 0.01
            else:
                self._fallback_threshold = SIMILARITY_THRESHOLD

        elif self.retrieval_mode == "hybrid":
            self.retriever = HybridRetriever()
            self.retriever.load_from_index()
            if not self.retriever.embedding_manager.available:
                self.retriever._fallback_threshold = 0.01
            else:
                self.retriever._fallback_threshold = SIMILARITY_THRESHOLD

        elif self.retrieval_mode == "lightrag":
            from lightrag_retriever import LightRAGRetriever
            self.retriever = LightRAGRetriever()
            self.retriever.load_from_index()

        else:
            raise ValueError(f"不支持的检索模式: {self.retrieval_mode}")


if __name__ == "__main__":
    print("RAG 检索模块测试")
    print(f"当前检索模式: {RETRIEVAL_MODE}")
