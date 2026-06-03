# RAG 检索器 RoleRetriever：
# 在 Milvus 中检索角色专属知识库（稠密向量 + 可选重排序）。


# 导入操作系统模块，用于读取环境变量
import os
# 导入Milvus向量数据库客户端，用于向量存储和检索
from pymilvus import MilvusClient
# 导入句向量模型库，用于生成文本的向量表示
from sentence_transformers import SentenceTransformer

# 导入角色配置工具，获取不同角色的Milvus集合配置
from role_config import get_role_config


# 角色专属检索器类：为每个AI角色提供专属的知识库检索能力
class RoleRetriever:
    # 初始化方法：根据角色代码创建检索器实例
    def __init__(self, role_code: str):
        # 获取当前角色的配置信息（如Milvus集合名）
        role = get_role_config(role_code)
        # 存储角色编码
        self.role_code = role_code
        # 从角色配置中获取对应的Milvus集合名称（每个角色独立知识库）
        self.collection_name = role["milvus_collection"]
        # 从环境变量读取Milvus服务地址，无则使用默认值
        milvus_uri = os.getenv("MILVUS_URI", "http://192.168.253.131:19530")
        # 初始化Milvus客户端为None
        self.client = None
        try:
            try:
                # 尝试创建带超时时间的Milvus客户端
                self.client = MilvusClient(uri=milvus_uri, timeout=8.0)
            except TypeError:
                # 捕获参数不兼容错误，创建无超时的基础客户端
                self.client = MilvusClient(uri=milvus_uri)
        except Exception as e:
            # 连接失败打印错误，客户端保持None
            print(f"[RAG] Milvus 不可用（role={role_code}）: {e}")

        # 初始化向量嵌入模型为None
        self._embedder = None
        # 初始化重排序模型为None
        self._reranker = None
        # 从环境变量读取向量模型路径，无则使用本地默认路径
        self._embedder_path = os.getenv("EMBEDDING_MODEL_PATH", "C:/Users/23672/Desktop/模型/bge-m3")
        # 从环境变量读取重排序模型路径，无则使用本地默认路径
        self._reranker_path = os.getenv("RERANKER_MODEL_PATH", "C:/Users/23672/Desktop/模型/bge-reranker-v2-m3")

    # 确保向量嵌入模型已加载（懒加载：使用时才加载，节省内存）
    def _ensure_embedder(self):
        # 模型未加载时，加载本地向量模型
        if self._embedder is None:
            self._embedder = SentenceTransformer(self._embedder_path, device="cpu")
        # 返回加载好的模型
        return self._embedder

    # 确保重排序模型已加载（懒加载+异常处理）
    def _ensure_reranker(self):
        # 标记为加载失败时，直接返回None
        if self._reranker is False:
            return None
        # 模型未加载时，尝试加载
        if self._reranker is None:
            try:
                # 加载本地重排序模型
                self._reranker = SentenceTransformer(self._reranker_path, device="cpu")
            except Exception:
                # 加载失败，标记为False，避免重复尝试
                self._reranker = False
                return None
        # 返回加载好的模型
        return self._reranker

    # 静态方法：将检索到的文档格式化为大模型可理解的上下文文本
    @staticmethod
    def format_docs_as_context(docs: list) -> str:
        # 无文档时返回默认提示
        if not docs:
            return "暂无可用专业参考内容。"
        # 初始化上下文片段列表
        context_parts = []
        # 遍历所有文档，拼接标题、来源、内容
        for doc in docs:
            context_parts.append(f"【{doc['title']}】（来源：{doc['source']}）\n{doc['content']}")
        # 用分隔符连接所有文档，返回格式化后的上下文
        return "\n\n---\n\n".join(context_parts)

    # 混合检索：向量检索 + 重排序（核心检索方法）
    def hybrid_search(self, query: str, top_k: int = 5):
        # Milvus客户端不可用时，返回空列表
        if self.client is None:
            return []
        try:
            # 检查对应角色的知识库集合是否存在
            if not self.client.has_collection(self.collection_name):
                return []
        except Exception as e:
            # 检查失败打印错误，返回空列表
            print(f"[RAG] has_collection 失败: {e}")
            return []

        try:
            # 获取向量嵌入模型
            embedder = self._ensure_embedder()
            # 将用户查询文本编码为归一化的稠密向量
            dense_vec = embedder.encode(query, normalize_embeddings=True)
            # 候选集数量：扩大3倍，为后续重排序提供更多候选
            candidate_k = max(top_k * 3, top_k)
            # 调用Milvus进行向量相似度检索
            results = self.client.search(
                collection_name=self.collection_name,  # 角色专属集合
                data=[dense_vec],                      # 查询向量
                anns_field="dense_vector",             # 向量字段名
                limit=candidate_k,                     # 返回候选数量
                output_fields=["title", "content", "source"],  # 需要返回的字段
            )
        except Exception as e:
            # 检索失败打印错误，返回空列表
            print(f"[RAG] search 失败: {e}")
            return []

        # 无检索结果时返回空
        if not results or not results[0]:
            return []

        # 整理Milvus返回结果为文档列表
        docs = []
        for hit in results[0]:
            docs.append(
                {
                    "content": hit["entity"].get("content", ""),   # 文档内容
                    "title": hit["entity"].get("title", ""),       # 文档标题
                    "source": hit["entity"].get("source", ""),     # 文档来源
                    "score": hit["distance"],                      # 向量相似度分数
                }
            )
        # 获取重排序模型
        reranker = self._ensure_reranker()
        # 模型可用且有文档时，执行重排序
        if reranker and docs:
            # 对查询进行重排序模型编码
            query_embedding = reranker.encode(query, normalize_embeddings=True)
            # 遍历文档，计算重排序分数
            for doc in docs:
                # 截取文档前512字符编码，避免过长
                doc_embedding = reranker.encode(doc["content"][:512], normalize_embeddings=True)
                # 计算向量点积作为重排序分数
                doc["rerank_score"] = float((query_embedding * doc_embedding).sum())
            # 按重排序分数降序排列（更相关的排前面）
            docs.sort(key=lambda x: x.get("rerank_score", -1.0), reverse=True)
        # 返回最终top_k个最相关的文档
        return docs[:top_k]

    # 对外检索接口：获取格式化后的上下文文本
    def retrieve_context(self, query: str) -> str:
        # 执行混合检索，获取top3文档
        docs = self.hybrid_search(query, top_k=3)
        # 格式化为上下文并返回
        return self.format_docs_as_context(docs)


# 测试代码：脚本独立运行时执行
if __name__ == "__main__":
    # 创建律师角色的检索器实例
    retriever = RoleRetriever("lawyer")
    # 测试查询语句
    query = "劳动合同到期不续签有赔偿吗"
    print("查询：", query)
    # 执行检索
    results = retriever.hybrid_search(query)
    # 遍历打印检索结果
    for r in results:
        print(f"标题: {r['title']}")
        print(f"分数: {r['score']:.4f}")
        print(f"内容: {r['content'][:150]}...")
        # 分隔线
        print("-" * 50)