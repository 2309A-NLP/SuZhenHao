# 配置文件
import os
from dotenv import load_dotenv

load_dotenv()

# DeepSeek API配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

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
EMBEDDINGS_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

# 检索配置
TOP_K = 5  # 返回前k个最相关的文档块
SIMILARITY_THRESHOLD = 0.3  # 相似度阈值

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
