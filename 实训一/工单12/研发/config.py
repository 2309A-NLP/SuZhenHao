# 配置文件
import os
from dotenv import load_dotenv

load_dotenv(override=True)

# DeepSeek API配置（两个Key分别用于不同模块）
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_KEY_2 = os.getenv("DEEPSEEK_API_KEY_2", "")
DEEPSEEK_API_BASE_2 = os.getenv("DEEPSEEK_API_BASE_2", "https://api.xiaomimimo.com/v1")
DEEPSEEK_MODEL_2 = os.getenv("DEEPSEEK_MODEL_2", "mimo-v2.5-pro")
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://token-plan-cn.xiaomimimo.com/v1")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "mimo-v2.5-pro")

# 文档配置 - 支持多PDF
PDF_DIR = "./data"
# 所有可用的PDF文件名（在 data/ 目录下）
PDF_FILES = [
    "招股说明书1-无水印.pdf",
    "招股说明书2.pdf",
]
# 当前激活的PDF文件列表（None = 全部）
ACTIVE_PDFS = None

CHUNK_SIZE = 800  # 文本分块大小
CHUNK_OVERLAP = 100  # 分块重叠

# 向量数据库配置
FAISS_INDEX_PATH = "./data/faiss_index"

# ── 检索配置 ─────────────────────────────────────────────
# 检索模式：vector（向量检索）/ bm25（全文检索）/ hybrid（混合检索）
RETRIEVAL_MODE = os.getenv("RETRIEVAL_MODE", "hybrid")

# 本地向量模型路径
EMBEDDINGS_MODEL = os.getenv("EMBEDDINGS_MODEL", r"C:\Users\23672\Desktop\模型\m3e-base")

# 本地重排模型路径（hybrid 模式使用）
RERANKER_MODEL = os.getenv("RERANKER_MODEL", r"C:\Users\23672\Desktop\模型\bge-reranker-base")

# 检索参数
TOP_K = 5  # 最终返回的文档块数量
BM25_TOP_K = 10  # BM25 / 向量检索初筛数量
RERANK_TOP_K = 3  # hybrid 模式 Reranker 精排后保留数量
SIMILARITY_THRESHOLD = 0.3  # 相似度阈值

# LightRAG 配置
LIGHTRAG_GRAPH_PATH = os.path.join(FAISS_INDEX_PATH, "lightrag_graph.json")
LIGHTRAG_ENTITY_TYPES = ["公司", "人物", "产品", "事件", "组织", "地点", "日期", "数字指标"]
LIGHTRAG_RELATION_TYPES = ["属于", "合作", "竞争", "投资", "担任", "产生", "位于", "提供", "开发", "收购"]
LIGHTRAG_TOP_K = 5  # 图检索返回数量
LIGHTRAG_HOP = 2  # 图检索跳数

# LLM生成配置
MAX_TOKENS = 1000
TEMPERATURE = 0.7

# 阿里云百炼 Qwen-VL 配置（图片理解）
QWEN_VL_API_KEY = os.getenv("QWEN_VL_API_KEY", "")
QWEN_VL_API_BASE = os.getenv("QWEN_VL_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
QWEN_VL_MODEL = os.getenv("QWEN_VL_MODEL", "qwen-vl-plus-latest")

# 图片配置
IMAGE_DIR = "./data/images"  # 图片上传存储目录
MAX_IMAGE_SIZE_MB = 10  # 最大图片大小（MB）
SUPPORTED_IMAGE_FORMATS = [".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"]
