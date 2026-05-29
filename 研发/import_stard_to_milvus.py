import json
import time
from sentence_transformers import SentenceTransformer
from pymilvus import MilvusClient

# ================== 配置 ==================
MILVUS_HOST = "192.168.253.131"
MILVUS_PORT = 19530
COLLECTION_NAME = "legal_knowledge_base"
MODEL_PATH = "C:/Users/23672/Desktop/模型/bge-m3"
DEVICE = "cuda"  # 如果有 GPU 则用 "cuda"，否则 "cpu"

# 直接指定 corpus.jsonl 的绝对路径
CORPUS_PATH = r"C:\Users\23672\Desktop\2309B\专高六\角色扮演系统\STARD\data\corpus.jsonl"

# 最多插入多少条（设为 None 则插入全部，建议先设为 1000 测试）
MAX_INSERT = 1000   # 先测试 1000 条，成功后再改为 None 或更大的数

BATCH_SIZE = 100

# 初始化模型和客户端
print("加载 BGE-M3 模型...")
model = SentenceTransformer(MODEL_PATH, device=DEVICE)
client = MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}")

if not client.has_collection(COLLECTION_NAME):
    raise RuntimeError(f"集合 {COLLECTION_NAME} 不存在，请先运行 milvus_setup.py")

buffer = []
count = 0

def insert_batch(batch):
    if not batch:
        return
    client.insert(COLLECTION_NAME, batch)
    print(f"✓ 已插入 {len(batch)} 条法规")

print(f"开始读取 {CORPUS_PATH} ...")
with open(CORPUS_PATH, 'r', encoding='utf-8') as f:
    for line_num, line in enumerate(f, 1):
        if MAX_INSERT and count >= MAX_INSERT:
            break
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            content = item.get("content", "")
            if not content:
                continue
            # 向量化
            dense_vec = model.encode(content, normalize_embeddings=True).tolist()
            data = {
                "doc_type": "law",
                "title": item.get("name", f"STARD_{item.get('id', line_num)}"),
                "source": "STARD",
                "content": content,
                "metadata": {"id": item.get("id")},
                "dense_vector": dense_vec,
                "sparse_vector": []
            }
            buffer.append(data)
            count += 1
            if len(buffer) >= BATCH_SIZE:
                insert_batch(buffer)
                buffer.clear()
        except Exception as e:
            print(f"第 {line_num} 行处理失败: {e}")

# 插入剩余数据
if buffer:
    insert_batch(buffer)

print(f"\n✅ 共插入 {count} 条记录。")