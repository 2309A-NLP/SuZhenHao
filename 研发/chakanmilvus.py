from pymilvus import MilvusClient

client = MilvusClient(uri="http://192.168.253.131:19530")
COLLECTION_NAME = "user_memory"

# 检查集合是否存在
if client.has_collection(COLLECTION_NAME):
    # 查询所有记录（最多100条）
    res = client.query(
        collection_name=COLLECTION_NAME,
        filter="",
        output_fields=["id", "user_id", "content", "memory_type", "importance", "created_at"],
        limit=100
    )
    if res:
        print(f"找到 {len(res)} 条长期记忆：")
        for item in res:
            print(f"ID: {item['id']}, 用户: {item['user_id']}, 类型: {item['memory_type']}")
            print(f"内容: {item['content']}")
            print(f"重要性: {item.get('importance', 'N/A')}, 创建时间: {item.get('created_at', 'N/A')}")
            print("---")
    else:
        print("长期记忆集合为空，尚未存储任何用户记忆。")
else:
    print("集合不存在，请先运行创建长期记忆集合脚本。")