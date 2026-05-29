from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType

MILVUS_HOST = "192.168.253.131"
MILVUS_PORT = 19530
COLLECTION_NAME = "conversation_history"

connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)

# 定义字段，增加一个虚拟向量字段（维度2，固定值）
fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="user_id", dtype=DataType.VARCHAR, max_length=64),
    FieldSchema(name="session_id", dtype=DataType.VARCHAR, max_length=64),
    FieldSchema(name="user_message", dtype=DataType.VARCHAR, max_length=65535),
    FieldSchema(name="assistant_response", dtype=DataType.VARCHAR, max_length=65535),
    FieldSchema(name="timestamp", dtype=DataType.INT64),
    FieldSchema(name="retrieved_sources", dtype=DataType.VARCHAR, max_length=4096),
    # 虚拟向量字段，满足 Milvus 必须有向量字段的要求
    FieldSchema(name="dummy_vector", dtype=DataType.FLOAT_VECTOR, dim=2),
]

# 创建集合
schema = CollectionSchema(fields, description="对话历史")
collection = Collection(COLLECTION_NAME, schema)

# 为虚拟向量创建索引（最小化资源）
index_params = {
    "metric_type": "L2",
    "index_type": "FLAT",
    "params": {}
}
collection.create_index("dummy_vector", index_params)

print(f"✅ 集合 '{COLLECTION_NAME}' 创建成功（含虚拟向量字段）")