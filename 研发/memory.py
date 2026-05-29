# 长期记忆 LongTermMemory：
# 把用户偏好、历史事实存入 Milvus 并支持向量召回。


# 导入时间模块，用于生成时间戳
import time
# 导入操作系统模块，用于读取环境变量
import os
# 导入 Milvus 客户端和数据类型，用于向量数据库操作
from pymilvus import MilvusClient, DataType
# 导入句向量模型，用于生成文本向量
from sentence_transformers import SentenceTransformer
# 导入 PyTorch，用于判断是否可用 GPU
import torch

# ================== 配置（直接写在文件中）==================
# 从环境变量获取 Milvus 主机地址，无则使用默认值
MILVUS_HOST = os.getenv("MILVUS_HOST", "192.168.253.131")
# 从环境变量获取 Milvus 端口，转为整型，无则使用默认值
MILVUS_PORT = int(os.getenv("MILVUS_PORT", "19530"))
# 从环境变量获取向量模型路径，无则使用本地路径
EMBEDDING_MODEL_PATH = os.getenv("EMBEDDING_MODEL_PATH", "C:/Users/23672/Desktop/模型/bge-m3")
# 定义记忆内容最大字节长度，用于截断文本
MAX_MEMORY_CONTENT_BYTES = 1024


def truncate_utf8_bytes(text: str, max_bytes: int) -> str:
    """按 UTF-8 字节长度截断，避免 Milvus varchar 超长报错。"""
    # 如果文本为空，直接返回空字符串
    if not text:
        return ""
    # 将文本编码为 UTF-8 字节串
    encoded = text.encode("utf-8")
    # 如果编码后长度不超过限制，直接返回原文本
    if len(encoded) <= max_bytes:
        return text
    # 截取最大字节长度
    truncated = encoded[:max_bytes]
    # 循环尝试解码，避免截断到不完整的 UTF-8 字符
    while truncated:
        try:
            # 尝试解码为字符串
            return truncated.decode("utf-8")
        except UnicodeDecodeError:
            # 解码失败则去掉最后一个字节，重试
            truncated = truncated[:-1]
    # 极端情况返回空字符串
    return ""

# ================== 长期记忆（Milvus）==================
# 长期记忆类，基于 Milvus 实现用户长期记忆存储与检索
class LongTermMemory:
    # 初始化方法，可指定角色代码，默认 default
    def __init__(self, role_code: str = "default"):
        # 保存角色编码
        self.role_code = role_code
        # 定义 Milvus 集合名称，按角色区分
        self.collection_name = f"user_memory_{role_code}"
        # 初始化 Milvus 客户端为 None
        self.client = None
        # 初始化向量模型为 None
        self.embedder = None
        # 初始化向量维度为 0
        self.dim = 0
        # 拼接 Milvus 连接地址
        uri = f"http://{MILVUS_HOST}:{MILVUS_PORT}"
        try:
            try:
                # 尝试创建带超时时间的 Milvus 客户端
                self.client = MilvusClient(uri=uri, timeout=8.0)
            except TypeError:
                # 捕获参数错误，创建不带超时的客户端
                self.client = MilvusClient(uri=uri)
        except Exception as e:
            # 连接失败打印日志，禁用长期记忆
            print(f"[LTM] Milvus 连接失败，长期记忆已禁用: {e}")
            return

        # 判断是否可用 GPU，优先使用 cuda
        device = "cuda" if torch.cuda.is_available() else "cpu"
        # 打印使用的设备
        print(f"使用设备: {device}")
        # 加载向量模型
        self.embedder = SentenceTransformer(EMBEDDING_MODEL_PATH, device=device)
        # 测试编码，获取向量维度
        self.dim = len(self.embedder.encode("test", normalize_embeddings=True).tolist())
        # 确保 Milvus 集合存在
        self._ensure_collection()

    # 确保集合存在，不存在则创建
    def _ensure_collection(self):
        # 客户端为空直接返回
        if not self.client:
            return
        try:
            # 判断集合是否不存在
            if not self.client.has_collection(self.collection_name):
                # 打印创建信息
                print(f"集合 '{self.collection_name}' 不存在，正在创建...")
                # 创建集合结构，自动生成 ID
                schema = self.client.create_schema(auto_id=True, enable_dynamic_field=False)
                # 添加主键 id 字段，自增整数
                schema.add_field("id", DataType.INT64, is_primary=True, auto_id=True)
                # 添加用户 id 字段，字符串类型
                schema.add_field("user_id", DataType.VARCHAR, max_length=64)
                # 添加记忆类型字段
                schema.add_field("memory_type", DataType.VARCHAR, max_length=32)
                # 添加记忆内容字段
                schema.add_field("content", DataType.VARCHAR, max_length=1024)
                # 添加重要度分数字段
                schema.add_field("importance", DataType.FLOAT)
                # 添加向量字段，维度为模型输出维度
                schema.add_field("embedding", DataType.FLOAT_VECTOR, dim=self.dim)
                # 添加创建时间戳字段
                schema.add_field("created_at", DataType.INT64)
                # 准备索引参数
                index_params = self.client.prepare_index_params()
                # 为向量字段添加 HNSW 索引，使用余弦相似度
                index_params.add_index("embedding", index_type="HNSW", metric_type="COSINE")
                # 创建集合
                self.client.create_collection(self.collection_name, schema=schema, index_params=index_params)
                # 打印创建成功信息
                print(f"集合 '{self.collection_name}' 创建成功。")
            else:
                # 集合已存在，打印信息
                print(f"集合 '{self.collection_name}' 已存在。")
        except Exception as e:
            # 异常则打印错误，禁用客户端和模型
            print(f"[LTM] 检查/创建集合失败，长期记忆已禁用: {e}")
            self.client = None
            self.embedder = None

    # 添加长期记忆
    def add_memory(self, user_id: str, memory_text: str, memory_type: str = "auto", importance: float = 0.5):
        # 客户端或模型未初始化，直接返回
        if not self.client or not self.embedder:
            return
        # 记忆内容为空，直接返回
        if not memory_text or memory_text.strip() == "":
            return
        # 按字节截断文本，避免超长
        text = truncate_utf8_bytes(memory_text.strip(), MAX_MEMORY_CONTENT_BYTES)
        # 截断后为空，直接返回
        if not text:
            return
        # 将文本编码为向量，并转为列表
        vec = self.embedder.encode(text, normalize_embeddings=True).tolist()
        # 构造插入数据
        data = {
            "user_id": user_id,
            "memory_type": memory_type,
            "content": text,
            "importance": importance,
            "embedding": vec,
            "created_at": int(time.time())
        }
        # 插入数据到 Milvus
        self.client.insert(self.collection_name, data)
        # 打印存储日志
        print(f"[长期记忆] 已存储 user={user_id}, type={memory_type}, text={text[:50]}...")

    # 检索用户相关的长期记忆
    def retrieve_memories(self, user_id: str, query: str, top_k: int = 3) -> list:
        # 客户端或模型未初始化，返回空列表
        if not self.client or not self.embedder:
            return []
        # 将查询文本编码为向量
        query_vec = self.embedder.encode(query, normalize_embeddings=True).tolist()
        # 执行向量搜索
        res = self.client.search(
            collection_name=self.collection_name,
            data=[query_vec],
            anns_field="embedding",
            filter=f"user_id == '{user_id}'",
            limit=top_k,
            output_fields=["content", "memory_type", "importance"]
        )
        # 无结果返回空列表
        if not res or not res[0]:
            return []
        # 提取记忆内容并返回
        return [hit["entity"]["content"] for hit in res[0]]

# ================== 测试代码（可选）==================
# 脚本主入口，仅在直接运行时执行
if __name__ == "__main__":
    # 创建长期记忆实例
    ltm = LongTermMemory()
    # 示例：插入一条测试记忆
    ltm.add_memory("test_user", "用户是程序员，经常加班", "test", 0.8)
    # 打印检索提示
    print("检索结果:")
    # 根据关键词检索用户记忆
    memories = ltm.retrieve_memories("test_user", "加班问题", top_k=2)
    # 遍历打印记忆
    for m in memories:
        print(m)