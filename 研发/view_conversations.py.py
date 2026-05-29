from pymilvus import connections, Collection

MILVUS_HOST = "192.168.253.131"
MILVUS_PORT = 19530
COLLECTION_NAME = "conversation_history"

# 连接到 Milvus
connections.connect(host=MILVUS_HOST, port=MILVUS_PORT)

# 获取集合对象
collection = Collection(COLLECTION_NAME)

# 加载集合到内存（关键步骤）
collection.load()

# 查询所有数据（最多100条）
results = collection.query(
    expr="",
    output_fields=["id", "user_id", "user_message", "assistant_response", "timestamp"],
    limit=100
)

print(f"共找到 {len(results)} 条对话记录\n")
for item in results:
    print(f"ID: {item['id']}")
    print(f"用户: {item['user_id']}")
    print(f"问题: {item['user_message']}")          # 去掉 [:100]
    print(f"回答: {item['assistant_response']}")    # 去掉 [:100]
    print(f"时间戳: {item['timestamp']}")
    print("-" * 50)