import os
from pymilvus import MilvusClient, DataType, Function, FunctionType
from sentence_transformers import SentenceTransformer

# ================== 1. 配置 ==================
MILVUS_HOST = '192.168.253.131'
MILVUS_PORT = '19530'
COLLECTION_NAME = "legal_knowledge_base"
DIM = 1024                          # BGE-M3 向量维度
DEVICE = 'cuda'                      # 或 'cuda'

# 本地 BGE-M3 模型路径
LOCAL_MODEL_PATH = 'C:/Users/23672/Desktop/模型/bge-m3'

# ================== 2. 加载模型 ==================
print(f"[1/5] 正在从本地加载 BGE-M3 模型: {LOCAL_MODEL_PATH} ...")
model = SentenceTransformer(LOCAL_MODEL_PATH, device=DEVICE)
print("[1/5] 模型加载完成。")

# ================== 3. 连接 Milvus ==================
print(f"[2/5] 正在连接到 Milvus 服务器 {MILVUS_HOST}:{MILVUS_PORT}...")
client = MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}", timeout=60)
print("[2/5] 连接成功。")

# ================== 4. 删除旧集合 ==================
if client.has_collection(COLLECTION_NAME):
    print(f"[3/5] 检测到已存在的集合 '{COLLECTION_NAME}'，正在删除...")
    client.drop_collection(COLLECTION_NAME)

# ================== 5. 创建 Schema ==================
print(f"[3/5] 正在创建集合 '{COLLECTION_NAME}' 的结构...")
schema = client.create_schema(auto_id=True, enable_dynamic_field=False)
schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
schema.add_field(field_name="doc_type", datatype=DataType.VARCHAR, max_length=32)
schema.add_field(field_name="title", datatype=DataType.VARCHAR, max_length=512)
schema.add_field(field_name="source", datatype=DataType.VARCHAR, max_length=256)
schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=65535)
schema.add_field(field_name="metadata", datatype=DataType.JSON)
schema.add_field(field_name="dense_vector", datatype=DataType.FLOAT_VECTOR, dim=DIM)
schema.add_field(field_name="sparse_vector", datatype=DataType.SPARSE_FLOAT_VECTOR)

# ================== 6. 定义 BM25 函数 ==================
bm25_function = Function(
    name="bm25_func",
    function_type=FunctionType.BM25,
    input_field_names=["content"],
    output_field_names=["sparse_vector"],
)

# ================== 7. 创建索引参数 ==================
print("[4/5] 正在创建索引参数...")
index_params = client.prepare_index_params()
# 稠密向量索引
index_params.add_index(
    field_name="dense_vector",
    index_type="HNSW",
    metric_type="COSINE",
    params={"M": 16, "efConstruction": 200}
)
# 稀疏向量索引（必须）
index_params.add_index(
    field_name="sparse_vector",
    index_type="SPARSE_INVERTED_INDEX",
    metric_type="IP",
    params={"drop_ratio_build": 0.0}
)

# ================== 8. 创建集合 ==================
client.create_collection(
    collection_name=COLLECTION_NAME,
    schema=schema,
    function=bm25_function,
    index_params=index_params
)

print("[5/5] 集合创建并加载完成。")
print(f"\n🎉 集合 '{COLLECTION_NAME}' 已在 Milvus 中成功创建！")