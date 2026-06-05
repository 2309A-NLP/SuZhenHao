"""
配置文件 - API密钥、模型路径等
"""

# ========== 小米 MiMo API 配置 ==========
MIMO_API_KEY = "tp-crncudh1306abwos94du3c0u7898mkyvxxn9pmq3klsqsnb3"
MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
MIMO_MODEL = "mimo-v2.5-pro"

# ========== Embedding 模型配置 ==========
# 使用本地 bge-small-zh 模型做中文向量化
EMBEDDING_MODEL_NAME = "bge-base-zh-v1.5"
EMBEDDING_MODEL_PATH = r"C:\Users\23672\Desktop\模型\bge-base-zh-v1.5"  # 本地模型路径

# ========== 文本分块参数 ==========
CHUNK_SIZE = 800       # 增大chunk数量，减少总块数
CHUNK_OVERLAP = 100    # 适当增加重叠保证上下文

# ========== RAG 检索参数 ==========
TOP_K = 4              # 检索最相关的K个文本块

# ========== 知识图谱参数 ==========
KG_TRIPLETS_PER_CHUNK = 5  # 每个chunk抽取的最大三元组数量
KG_MAX_CHUNKS = 20         # 最多处理的chunk数
KG_BATCH_SIZE = 3          # 每次API调用处理的chunk数（合并调用）

# ========== 语音识别配置 ==========
WHISPER_MODEL_SIZE = "base"  # tiny/base/small/medium/large

# ========== 文件路径 ==========
UPLOAD_DIR = "uploads"
VECTOR_STORE_DIR = "vector_store"
KG_OUTPUT_DIR = "kg_output"
