# -*- coding: utf-8 -*-
import json
from sentence_transformers import SentenceTransformer
from pymilvus import MilvusClient

# ================== 配置 ==================
MILVUS_HOST = '192.168.253.131'
MILVUS_PORT = '19530'
COLLECTION_NAME = "legal_knowledge_base"
DEVICE = 'cuda'
LOCAL_MODEL_PATH = 'C:/Users/23672/Desktop/模型/bge-m3'

# 初始化模型
print("正在加载 BGE-M3 模型...")
model = SentenceTransformer(LOCAL_MODEL_PATH, device=DEVICE)

# 连接 Milvus
client = MilvusClient(uri=f"http://{MILVUS_HOST}:{MILVUS_PORT}")

# 示例法律数据（实际使用时请替换为真实数据）
sample_laws = [
    {
        "doc_type": "law",
        "title": "劳动合同法第四十六条",
        "source": "中华人民共和国劳动合同法",
        "content": "第四十六条 有下列情形之一的，用人单位应当向劳动者支付经济补偿：（一）劳动者依照本法第三十八条规定解除劳动合同的；（二）用人单位依照本法第三十六条规定向劳动者提出解除劳动合同并与劳动者协商一致解除劳动合同的；（三）用人单位依照本法第四十条规定解除劳动合同的；（四）用人单位依照本法第四十一条第一款规定解除劳动合同的；（五）除用人单位维持或者提高劳动合同约定条件续订劳动合同，劳动者不同意续订的情形外，依照本法第四十四条第一项规定终止固定期限劳动合同的；（六）依照本法第四十四条第四项、第五项规定终止劳动合同的。",
        "metadata": {"law_id": "46"}
    },
    {
        "doc_type": "law",
        "title": "劳动合同法第四十七条",
        "source": "中华人民共和国劳动合同法",
        "content": "第四十七条 经济补偿按劳动者在本单位工作的年限，每满一年支付一个月工资。六个月以上不满一年的，按一年计算；不满六个月的，向劳动者支付半个月工资的经济补偿。",
        "metadata": {"law_id": "47"}
    },
    {
        "doc_type": "law",
        "title": "劳动合同法第三十九条",
        "source": "中华人民共和国劳动合同法",
        "content": "第三十九条 劳动者有下列情形之一的，用人单位可以解除劳动合同：（一）在试用期间被证明不符合录用条件的；（二）严重违反用人单位的规章制度的；（三）严重失职，营私舞弊，给用人单位造成重大损害的；（四）劳动者同时与其他用人单位建立劳动关系，对完成本单位的工作任务造成严重影响，或者经用人单位提出，拒不改正的；（五）因本法第二十六条第一款第一项规定的情形致使劳动合同无效的；（六）被依法追究刑事责任的。",
        "metadata": {"law_id": "39"}
    }
]

# 批量插入
print(f"准备插入 {len(sample_laws)} 条法律数据...")
for law in sample_laws:
    # 向量化
    dense_vec = model.encode(law["content"], normalize_embeddings=True)

    # 插入数据（sparse_vector 由 BM25 函数自动填充）
    data = {
        "doc_type": law["doc_type"],
        "title": law["title"],
        "source": law["source"],
        "content": law["content"],
        "metadata": law["metadata"],
        "dense_vector": dense_vec.tolist(),
        "sparse_vector": []
        # sparse_vector 不提供，由 BM25 函数自动生成
    }
    client.insert(COLLECTION_NAME, data)
    print(f"已插入: {law['title']}")

print("✅ 数据插入完成！")