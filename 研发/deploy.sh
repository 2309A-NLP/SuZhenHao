#!/bin/bash
# ============================================================
# 多角色 RAG 对话系统 - 一键部署脚本
# 适用于 Ubuntu 22.04 / WSL2
# 需要已安装 NVIDIA 驱动和 CUDA
# ============================================================

set -e  # 遇到错误立即退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# ------------------------------------------------------------
# 1. 环境检测
# ------------------------------------------------------------
log_info "检测系统环境..."

# 检测操作系统
if ! grep -qi "ubuntu" /etc/os-release; then
    log_warn "当前系统不是 Ubuntu，脚本可能无法正常运行"
fi

# 检测 Python3
if ! command -v python3 &> /dev/null; then
    log_error "Python3 未安装，请先安装: sudo apt install python3 python3-pip"
fi
PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
log_info "Python 版本: $PYTHON_VERSION"

# 检测 pip
if ! command -v pip3 &> /dev/null; then
    log_error "pip3 未安装"
fi

# 检测 GPU 和 CUDA
if command -v nvidia-smi &> /dev/null; then
    log_info "NVIDIA GPU 已检测到:"
    nvidia-smi --query-gpu=name --format=csv,noheader | head -1
else
    log_warn "未检测到 NVIDIA GPU，将使用 CPU 模式（性能较差）"
fi

# 检测 Docker（可选，用于一键启动依赖服务）
if command -v docker &> /dev/null && command -v docker-compose &> /dev/null; then
    log_info "Docker 和 Docker Compose 已安装，将使用容器化启动依赖服务"
    USE_DOCKER=true
else
    log_warn "Docker 未安装，将尝试使用系统包管理器安装 MySQL/Redis/Milvus（需要 sudo 权限）"
    USE_DOCKER=false
fi

# ------------------------------------------------------------
# 2. 创建虚拟环境并安装 Python 依赖
# ------------------------------------------------------------
log_info "创建 Python 虚拟环境..."
cd "$(dirname "$0")"  # 切换到脚本所在目录
PROJECT_ROOT=$(pwd)

# 如果已有虚拟环境，删除重建
if [ -d "venv" ]; then
    log_warn "删除旧虚拟环境"
    rm -rf venv
fi

python3 -m venv venv
source venv/bin/activate

log_info "升级 pip 并安装依赖..."
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    log_error "requirements.txt 不存在，请确保脚本在项目根目录下运行"
fi

# 额外安装 vLLM（可能不在 requirements.txt 中）
if command -v nvidia-smi &> /dev/null; then
    log_info "安装 vLLM (GPU 版本)..."
    pip install vllm
else
    log_info "安装 vLLM (CPU 版本)..."
    pip install vllm --extra-index-url https://download.pytorch.org/whl/cpu
fi

# 安装其他可能缺失的库
pip install pymysql redis pymilvus sentence-transformers fastapi uvicorn

log_info "Python 依赖安装完成"

# ------------------------------------------------------------
# 3. 启动依赖服务（MySQL, Redis, Milvus）
# ------------------------------------------------------------
start_services_docker() {
    log_info "使用 Docker Compose 启动依赖服务..."
    cat > docker-compose.yml <<EOF
version: '3.8'
services:
  mysql:
    image: mysql:8.0
    container_name: roleplay-mysql
    environment:
      MYSQL_ROOT_PASSWORD: root
      MYSQL_DATABASE: roleplay
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    container_name: roleplay-redis
    ports:
      - "6379:6379"
    restart: unless-stopped

  milvus:
    image: milvusdb/milvus:latest
    container_name: roleplay-milvus
    ports:
      - "19530:19530"
      - "9091:9091"
    environment:
      ETCD_ENDPOINTS: etcd:2379
      MINIO_ADDRESS: minio:9000
    depends_on:
      - etcd
      - minio
    restart: unless-stopped

  etcd:
    image: quay.io/coreos/etcd:v3.5.5
    container_name: roleplay-etcd
    environment:
      ETCD_AUTO_COMPACTION_MODE: revision
      ETCD_AUTO_COMPACTION_RETENTION: '1000'
      ETCD_QUOTA_BACKEND_BYTES: '4294967296'
      ETCD_SNAPSHOT_COUNT: '50000'
    volumes:
      - etcd_data:/etcd
    command: etcd -advertise-client-urls=http://127.0.0.1:2379 -listen-client-urls http://0.0.0.0:2379 --data-dir /etcd

  minio:
    image: minio/minio:latest
    container_name: roleplay-minio
    environment:
      MINIO_ACCESS_KEY: minioadmin
      MINIO_SECRET_KEY: minioadmin
    volumes:
      - minio_data:/minio_data
    command: minio server /minio_data --console-address ":9001"
    ports:
      - "9000:9000"
      - "9001:9001"

volumes:
  mysql_data:
  etcd_data:
  minio_data:
EOF
    docker-compose up -d
    log_info "等待服务启动（30秒）..."
    sleep 30
}

start_services_native() {
    log_info "使用系统服务启动 MySQL、Redis、Milvus..."
    # 安装 MySQL
    if ! command -v mysql &> /dev/null; then
        sudo apt update
        sudo apt install -y mysql-server
        sudo systemctl start mysql
        sudo systemctl enable mysql
        # 设置 root 密码（默认为空，这里设置为 root）
        sudo mysql -e "ALTER USER 'root'@'localhost' IDENTIFIED WITH mysql_native_password BY 'root'; FLUSH PRIVILEGES;"
        sudo mysql -e "CREATE DATABASE IF NOT EXISTS roleplay;"
    fi

    # 安装 Redis
    if ! command -v redis-server &> /dev/null; then
        sudo apt install -y redis-server
        sudo systemctl start redis
        sudo systemctl enable redis
    fi

    # 安装 Milvus（使用 Docker 单机版，因为 Milvus 官方推荐 Docker）
    if ! command -v docker &> /dev/null; then
        log_error "Milvus 需要 Docker，请先安装 Docker 或设置 USE_DOCKER=true"
    else
        docker run -d --name milvus_standalone \
            -p 19530:19530 -p 9091:9091 \
            milvusdb/milvus:latest
    fi
}

if [ "$USE_DOCKER" = true ]; then
    start_services_docker
else
    start_services_native
fi

# ------------------------------------------------------------
# 4. 初始化 MySQL 数据库表结构
# ------------------------------------------------------------
log_info "初始化 MySQL 数据库表..."
if [ -f "mysql_schema.sql" ]; then
    mysql -h127.0.0.1 -uroot -proot roleplay < mysql_schema.sql 2>/dev/null || \
    mysql -h127.0.0.1 -uroot -proot < mysql_schema.sql 2>/dev/null || \
    log_warn "MySQL 初始化失败，请手动执行: mysql -uroot -proot roleplay < mysql_schema.sql"
else
    log_warn "mysql_schema.sql 不存在，跳过"
fi

# 运行多角色迁移脚本（增加 role_code 字段等）
if [ -f "mysql_migrate_multi_role.py" ]; then
    python mysql_migrate_multi_role.py
fi

# ------------------------------------------------------------
# 5. 初始化 Milvus 集合
# ------------------------------------------------------------
log_info "初始化 Milvus 知识库集合..."
if [ -f "milvus_setup.py" ]; then
    python milvus_setup.py
fi
if [ -f "创建长期记忆集合.py" ]; then
    python 创建长期记忆集合.py
fi
if [ -f "create_conversation_collection.py" ]; then
    python create_conversation_collection.py
fi

# ------------------------------------------------------------
# 6. 下载/启动 vLLM 模型服务（后台运行）
# ------------------------------------------------------------
log_info "启动 vLLM 模型服务（Qwen3-0.6B）..."
# 检查模型是否已下载（这里假设模型存放在 ~/.cache/huggingface/ 或本地目录）
MODEL_NAME="Qwen/Qwen3-0.6B"
if [ ! -d "$HOME/.cache/huggingface/hub/models--Qwen--Qwen3-0.6B" ]; then
    log_info "首次运行将自动下载模型，可能需要几分钟..."
fi

# 使用 nohup 后台运行 vLLM 服务，日志输出到 vllm.log
nohup python -m vllm.entrypoints.openai.api_server \
    --model $MODEL_NAME \
    --served-model-name Qwen/Qwen3-0.6B \
    --host 0.0.0.0 \
    --port 8000 \
    --max-model-len 2048 \
    --gpu-memory-utilization 0.8 \
    > vllm.log 2>&1 &

VLLM_PID=$!
log_info "vLLM 服务已启动，PID: $VLLM_PID，日志: vllm.log"

# 等待 vLLM 服务就绪
log_info "等待 vLLM 服务就绪（最多 120 秒）..."
for i in {1..120}; do
    if curl -s http://localhost:8000/health > /dev/null 2>&1; then
        log_info "vLLM 服务已就绪"
        break
    fi
    sleep 1
    if [ $i -eq 120 ]; then
        log_warn "vLLM 服务启动超时，请检查日志 vllm.log"
    fi
done

# ------------------------------------------------------------
# 7. 设置环境变量并启动 FastAPI 前端
# ------------------------------------------------------------
log_info "设置环境变量并启动 FastAPI 服务..."
export VLLM_BASE_URL="http://localhost:8000/v1"
export VLLM_API_KEY="EMPTY"
export VLLM_MODEL_NAME="Qwen/Qwen3-0.6B"
export MYSQL_HOST="127.0.0.1"
export MYSQL_PORT="3306"
export MYSQL_USER="root"
export MYSQL_PASSWORD="root"
export MYSQL_DB="roleplay"
export MILVUS_URI="http://localhost:19530"
export REDIS_HOST="localhost"
export REDIS_PORT="6379"

# 启动 FastAPI 服务（使用 uvicorn，前台运行）
log_info "启动 FastAPI 主服务，访问 http://localhost:8080"
uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# ------------------------------------------------------------
# 8. 清理函数（按 Ctrl+C 时调用）
# ------------------------------------------------------------
cleanup() {
    log_info "正在关闭服务..."
    kill $VLLM_PID 2>/dev/null || true
    if [ "$USE_DOCKER" = true ]; then
        docker-compose down
    fi
    exit 0
}
trap cleanup SIGINT SIGTERM

# 脚本结束