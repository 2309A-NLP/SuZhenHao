# 配置文件
import os
from dotenv import load_dotenv

load_dotenv()

# DeepSeek API配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_API_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 文档配置
PDF_PATH = os.getenv("PDF_PATH", "./data/招股说明书1-无水印.pdf")
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
