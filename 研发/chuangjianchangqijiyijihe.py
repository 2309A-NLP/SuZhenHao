# -*- coding: utf-8 -*-
# user_memory_setup.py
from pymilvus import MilvusClient, DataType

MILVUS_HOST = "192.168.253.131"  # 你的 Milvus IP
MILVUS_PORT = "19530"
COLLECTION_NAME = "user_memory"

print(f"正在连接到 Milvus 服务器 {MILVUS_HOST}:{MILVUS_PORT}...")
client = MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}", timeout=60)

# 如果已存在就删除（方便重新运行）
if client.has_collection(COLLECTION_NAME):
    print(f"集合 '{COLLECTION_NAME}' 已存在，正在删除...")
    client.drop_collection(COLLECTION_NAME)

# 定义 Schema（数据结构）
schema = client.create_schema(auto_id=True, enable_dynamic_field=False)
schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
schema.add_field(field_name="user_id", datatype=DataType.VARCHAR, max_length=64)
schema.add_field(field_name="memory_type", datatype=DataType.VARCHAR, max_length=32)
schema.add_field(field_name="content", datatype=DataType.VARCHAR, max_length=1024)
schema.add_field(field_name="importance", datatype=DataType.FLOAT)
schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=1024)  # 根据BGE-M3的维度
schema.add_field(field_name="created_at", datatype=DataType.INT64)

# 创建索引，以加快检索速度
index_params = client.prepare_index_params()
index_params.add_index(field_name="embedding", index_type="HNSW", metric_type="COSINE")

# 创建集合
client.create_collection(
    collection_name=COLLECTION_NAME,
    schema=schema,
    index_params=index_params
)

print(f"🎉 集合 '{COLLECTION_NAME}' 创建成功！")