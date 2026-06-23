#!/bin/bash
# ============================================================================
# RAGFlow DeepDoc 一键部署脚本 v2.0
# 版本：v2.0.0
# 适用环境：Linux / WSL2 Ubuntu / macOS
# 项目：RAGFlow DeepDoc 深度文档解析系统
# 生成时间：2026年6月23日
# ============================================================================
#
# 使用方法：
#   chmod +x deploy_ragflow_v2.sh
#   ./deploy_ragflow_v2.sh                    # CPU 模式，默认配置
#   ./deploy_ragflow_v2.sh --gpu              # GPU 模式
#   ./deploy_ragflow_v2.sh --dir /opt/ragflow # 自定义安装目录
#   ./deploy_ragflow_v2.sh --llm-openai --api-key sk-xxx  # 配置 LLM
#   ./deploy_ragflow_v2.sh --check            # 仅检查环境，不部署
#   ./deploy_ragflow_v2.sh --stop             # 停止所有服务
#   ./deploy_ragflow_v2.sh --restart          # 重启所有服务
#   ./deploy_ragflow_v2.sh --status           # 查看服务状态
#   ./deploy_ragflow_v2.sh --logs             # 查看实时日志
#   ./deploy_ragflow_v2.sh --backup           # 备份数据
#   ./deploy_ragflow_v2.sh --restore <file>   # 恢复数据
#   ./deploy_ragflow_v2.sh --uninstall        # 完全卸载
# ============================================================================

set -euo pipefail

# ============================================================================
# 全局配置
# ============================================================================
SCRIPT_VERSION="2.0.0"
RAGFLOW_VERSION="v0.23.1"
RAGFLOW_IMAGE="infiniflow/ragflow:${RAGFLOW_VERSION}"
INSTALL_DIR="${HOME}/ragflow"
REPO_URL="https://github.com/infiniflow/ragflow.git"
BACKUP_DIR="${HOME}/ragflow-backups"
LOG_FILE="${HOME}/ragflow-deploy-$(date +%Y%m%d%H%M%S).log"

# 端口配置
WEB_HTTP_PORT=80
WEB_HTTPS_PORT=443
API_PORT=9380
ADMIN_PORT=9381
MCP_PORT=9382
ES_PORT=1200
MYSQL_PORT=5455
MINIO_API_PORT=9003
MINIO_CONSOLE_PORT=9004
REDIS_PORT=6379

# 密码配置（自动生成强密码）
MYSQL_PASSWORD=""
ES_PASSWORD=""
MINIO_USER="rag_flow"
MINIO_PASSWORD=""
REDIS_PASSWORD=""

# 资源配置
MEM_LIMIT="8073741824"  # 8GB
ES_JAVA_OPTS="-Xms4g -Xmx4g"
DEVICE="cpu"

# Embedding 模型配置
TEI_EMBEDDING_MODEL="Qwen/Qwen3-Embedding-0.6B"
COMPOSE_PROFILES=""

# LLM 配置
LLM_FACTORY=""
LLM_API_KEY=""
LLM_BASE_URL=""
LLM_CHAT_MODEL=""
LLM_EMBEDDING_MODEL=""

# 操作模式
ACTION="deploy"

# ============================================================================
# 颜色定义
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

# ============================================================================
# 日志函数
# ============================================================================
log_info()    { echo -e "${GREEN}[INFO]${NC} $1" | tee -a "$LOG_FILE"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"; }
log_step()    { echo -e "\n${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}" | tee -a "$LOG_FILE"
                echo -e "${CYAN}${BOLD}  Step $1${NC}" | tee -a "$LOG_FILE"
                echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n" | tee -a "$LOG_FILE"; }
log_success() { echo -e "${GREEN}${BOLD}✅ $1${NC}" | tee -a "$LOG_FILE"; }
log_banner()  { echo -e "${MAGENTA}${BOLD}$1${NC}" | tee -a "$LOG_FILE"; }

# ============================================================================
# 工具函数
# ============================================================================

# 生成随机密码
generate_password() {
    local length=${1:-16}
    openssl rand -base64 32 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c "$length"
}

# 检查端口是否被占用
check_port() {
    local port=$1
    local service=$2
    if ss -tlnp 2>/dev/null | grep -q ":${port} " || netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
        local pid=$(ss -tlnp 2>/dev/null | grep ":${port} " | awk '{print $NF}' | grep -oP 'pid=\K\d+' | head -1)
        log_warn "端口 ${port} 已被占用（${service}），PID: ${pid:-unknown}"
        return 1
    fi
    return 0
}

# 等待服务就绪
wait_for_service() {
    local service_name=$1
    local url=$2
    local max_wait=${3:-120}
    local elapsed=0

    echo -n "  等待 ${service_name} 就绪 "
    while [[ $elapsed -lt $max_wait ]]; do
        if curl -s -o /dev/null -w "%{http_code}" "$url" 2>/dev/null | grep -q "200\|301\|302\|401"; then
            echo -e " ${GREEN}✓${NC} (${elapsed}s)"
            return 0
        fi
        sleep 3
        elapsed=$((elapsed + 3))
        echo -n "."
    done
    echo -e " ${RED}✗ 超时${NC} (${max_wait}s)"
    return 1
}

# 保存密码到文件
save_credentials() {
    local cred_file="${INSTALL_DIR}/docker/.credentials"
    cat > "$cred_file" << EOF
# ============================================================================
# RAGFlow 凭据文件（请妥善保管！）
# 生成时间：$(date '+%Y-%m-%d %H:%M:%S')
# ============================================================================

MySQL 密码:     ${MYSQL_PASSWORD}
ES 密码:        ${ES_PASSWORD}
MinIO 用户:     ${MINIO_USER}
MinIO 密码:     ${MINIO_PASSWORD}
Redis 密码:     ${REDIS_PASSWORD}

Web UI:         http://localhost:${WEB_HTTP_PORT}
API:            http://localhost:${API_PORT}
Admin:          http://localhost:${ADMIN_PORT}
MinIO Console:  http://localhost:${MINIO_CONSOLE_PORT}

管理员账号:     admin
管理员密码:     admin（请首次登录后修改！）
EOF
    chmod 600 "$cred_file"
    log_info "凭据已保存到: ${cred_file}"
}

# ============================================================================
# Step 1: 检查系统要求
# ============================================================================
check_system_requirements() {
    log_step "1/10 — 检查系统要求"

    # 操作系统
    local os_type=$(uname -s)
    local os_release=""
    if [[ -f /etc/os-release ]]; then
        os_release=$(. /etc/os-release && echo "$PRETTY_NAME")
    fi
    log_info "操作系统: ${os_type} ${os_release:-$(uname -r)}"

    # CPU 核心数
    local cpu_cores=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo "unknown")
    log_info "CPU 核心数: ${cpu_cores}"
    if [[ "$cpu_cores" -lt 4 ]]; then
        log_warn "CPU 核心数少于 4 个，可能影响文档解析性能"
    fi

    # 内存
    local total_mem_kb=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo "0")
    local total_mem_gb=$((total_mem_kb / 1024 / 1024))
    log_info "系统内存: ${total_mem_gb} GB"
    if [[ "$total_mem_gb" -lt 16 ]]; then
        log_warn "系统内存少于 16 GB，建议至少 16 GB（推荐 32 GB）"
    fi

    # 磁盘空间
    local disk_avail=$(df -BG "${HOME}" 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G' || echo "0")
    log_info "可用磁盘空间: ${disk_avail} GB"
    if [[ "$disk_avail" -lt 50 ]]; then
        log_warn "可用磁盘空间少于 50 GB，建议至少 50 GB（推荐 100 GB SSD）"
    fi

    # Docker
    if ! command -v docker &>/dev/null; then
        log_error "Docker 未安装！"
        echo ""
        echo "  安装方法："
        echo "  # Ubuntu/Debian:"
        echo "  curl -fsSL https://get.docker.com | sh"
        echo "  sudo usermod -aG docker \$USER"
        echo "  # 然后重新登录"
        echo ""
        echo "  # macOS:"
        echo "  brew install --cask docker"
        echo ""
        exit 1
    fi

    local docker_version=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unknown")
    log_info "Docker 版本: ${docker_version}"

    # Docker Compose
    if docker compose version &>/dev/null; then
        local compose_version=$(docker compose version --short 2>/dev/null || echo "unknown")
        log_info "Docker Compose 版本: ${compose_version}"
    elif command -v docker-compose &>/dev/null; then
        local compose_version=$(docker-compose version --short 2>/dev/null || echo "unknown")
        log_info "Docker Compose (旧版): ${compose_version}"
        log_warn "建议升级到 Docker Compose V2"
    else
        log_error "Docker Compose 未安装！"
        exit 1
    fi

    # Docker 守护进程状态
    if ! docker info &>/dev/null; then
        log_error "Docker 守护进程未运行！"
        echo "  请执行: sudo systemctl start docker"
        exit 1
    fi

    # Git
    if ! command -v git &>/dev/null; then
        log_warn "Git 未安装，将尝试安装..."
        sudo apt-get update -qq && sudo apt-get install -y -qq git
    fi
    log_info "Git 版本: $(git --version | awk '{print $3}')"

    # 端口检查
    log_info "检查关键端口..."
    local ports_ok=true
    check_port "$WEB_HTTP_PORT" "Web UI" || ports_ok=false
    check_port "$API_PORT" "API Server" || ports_ok=false
    check_port "$ES_PORT" "Elasticsearch" || ports_ok=false
    check_port "$MYSQL_PORT" "MySQL" || ports_ok=false
    check_port "$REDIS_PORT" "Redis" || ports_ok=false
    check_port "$MINIO_API_PORT" "MinIO" || ports_ok=false

    if [[ "$ports_ok" == "false" ]]; then
        log_warn "部分端口已被占用，可能需要修改 .env 中的端口配置"
    fi

    log_success "系统要求检查完成"
}

# ============================================================================
# Step 2: 配置系统参数
# ============================================================================
configure_system() {
    log_step "2/10 — 配置系统参数"

    # vm.max_map_count（Elasticsearch 必需）
    local current_val=$(sysctl -n vm.max_map_count 2>/dev/null || echo "0")
    log_info "当前 vm.max_map_count: ${current_val}"

    if [[ "$current_val" -lt 262144 ]]; then
        log_info "设置 vm.max_map_count = 262144 ..."
        sudo sysctl -w vm.max_map_count=262144

        # 持久化
        if ! grep -q "vm.max_map_count=262144" /etc/sysctl.conf 2>/dev/null; then
            echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf > /dev/null
            log_info "已持久化到 /etc/sysctl.conf"
        fi
        log_success "vm.max_map_count 设置完成"
    else
        log_success "vm.max_map_count 已满足要求 (>= 262144)"
    fi

    # 文件描述符限制
    local ulimit_n=$(ulimit -n 2>/dev/null || echo "0")
    log_info "当前文件描述符限制: ${ulimit_n}"
    if [[ "$ulimit_n" -lt 65536 ]]; then
        log_warn "文件描述符限制较低，建议设置为 65536+"
        echo "  临时设置: ulimit -n 65536"
        echo "  永久设置: 在 /etc/security/limits.conf 中添加:"
        echo "    * soft nofile 65536"
        echo "    * hard nofile 65536"
    fi
}

# ============================================================================
# Step 3: GPU 配置（可选）
# ============================================================================
setup_gpu() {
    log_step "3/10 — GPU 配置检查"

    if [[ "$DEVICE" != "gpu" ]]; then
        log_info "当前为 CPU 模式，跳过 GPU 配置"
        log_info "如需 GPU 模式，请使用 --gpu 参数重新运行"
        return 0
    fi

    # 检查 NVIDIA 驱动
    if ! command -v nvidia-smi &>/dev/null; then
        log_error "NVIDIA 驱动未安装！"
        echo ""
        echo "  GPU 模式需要："
        echo "  1. NVIDIA GPU 驱动 (>= 525.60)"
        echo "  2. CUDA Toolkit (>= 12.0)"
        echo "  3. nvidia-container-toolkit"
        echo ""
        echo "  安装驱动: https://www.nvidia.com/Download/index.aspx"
        echo "  安装 CUDA: https://developer.nvidia.com/cuda-downloads"
        exit 1
    fi

    local gpu_info=$(nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader 2>/dev/null || echo "unknown")
    log_info "GPU 信息: ${gpu_info}"

    local gpu_mem=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1 | awk '{print $1}')
    log_info "GPU 显存: ${gpu_mem}"

    # 检查 nvidia-container-toolkit
    if command -v nvidia-ctk &>/dev/null; then
        log_success "nvidia-container-toolkit 已安装"
    else
        log_info "安装 nvidia-container-toolkit ..."

        # 检测发行版
        local distro=""
        if [[ -f /etc/debian_version ]]; then
            distro="debian"
        elif [[ -f /etc/redhat-release ]]; then
            distro="redhat"
        fi

        if [[ "$distro" == "debian" ]]; then
            curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
                sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

            curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
                sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
                sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null

            sudo apt-get update -qq
            sudo apt-get install -y -qq nvidia-container-toolkit
        else
            log_error "请手动安装 nvidia-container-toolkit"
            echo "  参考: https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html"
            exit 1
        fi

        # 配置 Docker 运行时
        sudo nvidia-ctk runtime configure --runtime=docker
        sudo systemctl restart docker

        log_success "nvidia-container-toolkit 安装完成"
    fi

    # Docker GPU 测试
    log_info "测试 Docker GPU 访问..."
    if docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi &>/dev/null; then
        log_success "Docker GPU 访问测试通过"
    else
        log_error "Docker GPU 访问测试失败"
        echo "  请检查: docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi"
        exit 1
    fi
}

# ============================================================================
# Step 4: 获取 RAGFlow 部署文件
# ============================================================================
clone_repository() {
    log_step "4/10 — 获取 RAGFlow 部署文件"

    if [[ -d "${INSTALL_DIR}" ]]; then
        log_info "安装目录已存在: ${INSTALL_DIR}"
        cd "${INSTALL_DIR}"

        if [[ -d ".git" ]]; then
            local current_branch=$(git branch --show-current 2>/dev/null || echo "unknown")
            log_info "当前分支: ${current_branch}"

            log_info "拉取最新代码..."
            git fetch --all --tags 2>/dev/null || true

            # 尝试切换到指定版本
            if git rev-parse "$RAGFLOW_VERSION" >/dev/null 2>&1; then
                git checkout "$RAGFLOW_VERSION" 2>/dev/null
                log_info "已切换到版本: ${RAGFLOW_VERSION}"
            else
                git pull origin main 2>/dev/null || true
                log_info "使用最新代码"
            fi
        else
            log_info "目录存在但不是 Git 仓库，使用现有文件"
        fi
    else
        log_info "克隆 RAGFlow 仓库..."
        git clone --depth 1 --branch "$RAGFLOW_VERSION" "$REPO_URL" "${INSTALL_DIR}" 2>/dev/null || \
        git clone "$REPO_URL" "${INSTALL_DIR}"
        cd "${INSTALL_DIR}"
        git checkout "$RAGFLOW_VERSION" 2>/dev/null || log_info "使用默认分支"
    fi

    # 确保在 docker 目录
    if [[ ! -d "docker" ]]; then
        log_error "docker 目录不存在，请检查仓库完整性"
        exit 1
    fi

    cd docker/
    log_success "仓库准备完成: ${INSTALL_DIR}/docker"
}

# ============================================================================
# Step 5: 生成密码和环境配置
# ============================================================================
generate_env_file() {
    log_step "5/10 — 生成环境配置文件"

    local env_file="${INSTALL_DIR}/docker/.env"

    # 生成密码（如果未设置）
    if [[ -z "$MYSQL_PASSWORD" ]]; then
        MYSQL_PASSWORD=$(generate_password 16)
    fi
    if [[ -z "$ES_PASSWORD" ]]; then
        ES_PASSWORD=$(generate_password 16)
    fi
    if [[ -z "$MINIO_PASSWORD" ]]; then
        MINIO_PASSWORD=$(generate_password 16)
    fi
    if [[ -z "$REDIS_PASSWORD" ]]; then
        REDIS_PASSWORD=$(generate_password 16)
    fi

    # 备份已有配置
    if [[ -f "$env_file" ]]; then
        local backup="${env_file}.bak.$(date +%Y%m%d%H%M%S)"
        cp "$env_file" "$backup"
        log_info "已备份原有 .env 文件到: ${backup}"
    fi

    cat > "$env_file" << EOF
# ============================================================================
# RAGFlow 环境配置文件
# 生成时间：$(date '+%Y-%m-%d %H:%M:%S')
# 脚本版本：${SCRIPT_VERSION}
# ============================================================================

# ---- 镜像版本 ----
RAGFLOW_IMAGE=${RAGFLOW_IMAGE}

# ---- 运行设备 ----
DEVICE=${DEVICE}

# ---- 文档存储引擎 ----
DOC_ENGINE=elasticsearch

# ---- 容器内存限制 ----
MEM_LIMIT=${MEM_LIMIT}

# ---- 时区 ----
TZ=Asia/Shanghai

# ============================================================================
# 端口配置
# ============================================================================
SVR_WEB_HTTP_PORT=${WEB_HTTP_PORT}
SVR_WEB_HTTPS_PORT=${WEB_HTTPS_PORT}
SVR_HTTP_PORT=${API_PORT}
ADMIN_SVR_HTTP_PORT=${ADMIN_PORT}
SVR_MCP_PORT=${MCP_PORT}
SVR_ES_PORT=${ES_PORT}
SVR_MYSQL_PORT=${MYSQL_PORT}
MINIO_PORT=${MINIO_API_PORT}
MINIO_CONSOLE_PORT=${MINIO_CONSOLE_PORT}
SVR_REDIS_PORT=${REDIS_PORT}

# ============================================================================
# 密码配置（已自动生成强密码）
# ============================================================================
MYSQL_PASSWORD=${MYSQL_PASSWORD}
ES_PASSWORD=${ES_PASSWORD}
MINIO_USER=${MINIO_USER}
MINIO_PASSWORD=${MINIO_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}

# ============================================================================
# 功能开关
# ============================================================================
REGISTER_ENABLED=1
USE_DOCLING=false

# ============================================================================
# Embedding 服务配置
# ============================================================================
COMPOSE_PROFILES=${COMPOSE_PROFILES}
TEI_EMBEDDING_MODEL_NAME=${TEI_EMBEDDING_MODEL}
EOF

    log_success "环境配置文件已生成: ${env_file}"
}

# ============================================================================
# Step 6: 生成服务配置文件
# ============================================================================
generate_service_conf() {
    log_step "6/10 — 生成服务配置文件"

    local conf_file="${INSTALL_DIR}/docker/service_conf.yaml.template"

    # 确定 LLM 配置
    local factory="${LLM_FACTORY:-OpenAI}"
    local api_key="${LLM_API_KEY:-your-api-key-here}"
    local base_url="${LLM_BASE_URL:-https://api.openai.com/v1}"
    local chat_model="${LLM_CHAT_MODEL:-gpt-4o}"

    cat > "$conf_file" << EOF
# ============================================================================
# RAGFlow 服务配置文件
# 生成时间：$(date '+%Y-%m-%d %H:%M:%S')
# ============================================================================

# ---- Elasticsearch 配置 ----
es:
  hosts: http://es01:9200
  username: elastic
  password: ${ES_PASSWORD}

# ---- MySQL 配置 ----
mysql:
  host: mysql
  port: 3306
  user: root
  password: ${MYSQL_PASSWORD}
  database: rag_flow

# ---- Redis 配置 ----
redis:
  host: redis
  port: 6379
  password: ${REDIS_PASSWORD}

# ---- MinIO 配置 ----
minio:
  host: minio
  port: 9000
  user: ${MINIO_USER}
  password: ${MINIO_PASSWORD}

# ============================================================================
# LLM 模型配置
# ============================================================================
user_default_llm:
  factory: '${factory}'
  api_key: '${api_key}'
  base_url: '${base_url}'
  default_models:
    chat_model:
      name: '${chat_model}'
      factory: '${factory}'
      api_key: '${api_key}'
      base_url: '${base_url}'
    embedding_model:
      api_key: '${api_key}'
      base_url: 'http://tei:80'
    rerank_model: 'bge-reranker-v2-m3'
    image2text_model: ''
    asr_model: ''
EOF

    log_success "服务配置文件已生成: ${conf_file}"
}

# ============================================================================
# Step 7: 拉取镜像
# ============================================================================
pull_images() {
    log_step "7/10 — 拉取 Docker 镜像"

    cd "${INSTALL_DIR}/docker"

    log_info "拉取 RAGFlow 镜像: ${RAGFLOW_IMAGE}"
    log_info "这可能需要几分钟，请耐心等待..."

    if [[ "$DEVICE" == "gpu" ]]; then
        docker compose --profile ragflow-gpu -f docker-compose.yml pull 2>&1 | tee -a "$LOG_FILE"
    else
        docker compose -f docker-compose.yml pull 2>&1 | tee -a "$LOG_FILE"
    fi

    log_success "镜像拉取完成"
}

# ============================================================================
# Step 8: 启动服务
# ============================================================================
start_services() {
    log_step "8/10 — 启动 RAGFlow 服务"

    cd "${INSTALL_DIR}/docker"

    # 启动服务
    log_info "启动所有服务..."
    if [[ "$DEVICE" == "gpu" ]]; then
        docker compose --profile ragflow-gpu -f docker-compose.yml up -d 2>&1 | tee -a "$LOG_FILE"
    else
        docker compose -f docker-compose.yml up -d 2>&1 | tee -a "$LOG_FILE"
    fi

    log_success "服务启动命令已执行"
}

# ============================================================================
# Step 9: 验证部署
# ============================================================================
verify_deployment() {
    log_step "9/10 — 验证部署状态"

    cd "${INSTALL_DIR}/docker"

    # 等待服务启动
    log_info "等待服务启动（最多 180 秒）..."
    local max_wait=180
    local elapsed=0

    while [[ $elapsed -lt $max_wait ]]; do
        local all_running=true
        local unhealthy=0

        # 检查容器状态
        while IFS= read -r line; do
            local status=$(echo "$line" | grep -oP '"Status":"[^"]*"' | cut -d'"' -f4)
            if [[ "$status" != "running" ]]; then
                all_running=false
            fi
            if echo "$line" | grep -q '"unhealthy"'; then
                unhealthy=$((unhealthy + 1))
            fi
        done < <(docker compose ps --format json 2>/dev/null || echo "")

        if [[ "$all_running" == "true" && "$unhealthy" -eq 0 ]]; then
            break
        fi

        sleep 5
        elapsed=$((elapsed + 5))
        echo -n "."
    done
    echo ""

    # 显示容器状态
    echo ""
    log_info "容器运行状态："
    docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}" 2>/dev/null || \
    docker compose ps

    echo ""

    # 检查各服务端口
    log_info "端口检查："
    local services=(
        "Web UI:${WEB_HTTP_PORT}"
        "API:${API_PORT}"
        "Admin:${ADMIN_PORT}"
        "Elasticsearch:${ES_PORT}"
        "MySQL:${MYSQL_PORT}"
        "Redis:${REDIS_PORT}"
        "MinIO API:${MINIO_API_PORT}"
        "MinIO Console:${MINIO_CONSOLE_PORT}"
    )

    local all_ok=true
    for svc in "${services[@]}"; do
        local name="${svc%%:*}"
        local port="${svc##*:}"
        if ss -tlnp 2>/dev/null | grep -q ":${port} " || netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
            echo -e "  ${GREEN}✓${NC} ${name} (端口 ${port}) — ${GREEN}运行中${NC}"
        else
            echo -e "  ${RED}✗${NC} ${name} (端口 ${port}) — ${RED}未监听${NC}"
            all_ok=false
        fi
    done

    # 检查 Elasticsearch 健康状态
    echo ""
    log_info "Elasticsearch 集群健康检查："
    local es_health=$(curl -s -u "elastic:${ES_PASSWORD}" "http://localhost:${ES_PORT}/_cluster/health?pretty" 2>/dev/null || echo "无法连接")
    echo "$es_health" | head -8

    # 保存凭据
    save_credentials

    echo ""
    log_banner "╔══════════════════════════════════════════════════════════════╗"
    log_banner "║                                                              ║"
    log_banner "║          🎉  RAGFlow 部署完成！                               ║"
    log_banner "║                                                              ║"
    log_banner "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo -e "  ${BOLD}📌 访问地址:${NC}"
    echo -e "     Web UI:         http://localhost:${WEB_HTTP_PORT}"
    echo -e "     API 服务:       http://localhost:${API_PORT}"
    echo -e "     管理后台:       http://localhost:${ADMIN_PORT}"
    echo -e "     MinIO 控制台:   http://localhost:${MINIO_CONSOLE_PORT}"
    echo ""
    echo -e "  ${BOLD}📌 默认管理员:${NC}"
    echo -e "     账号: admin"
    echo -e "     密码: admin"
    echo ""
    echo -e "  ${BOLD}📌 凭据文件:${NC} ${INSTALL_DIR}/docker/.credentials"
    echo ""
    echo -e "  ${YELLOW}⚠  首次登录后请立即修改默认管理员密码！${NC}"
    echo -e "  ${YELLOW}⚠  生产环境请修改 .env 中的所有密码配置！${NC}"
    echo ""
}

# ============================================================================
# Step 10: 输出后续操作指南
# ============================================================================
show_next_steps() {
    log_step "10/10 — 后续操作指南"

    echo -e "  ${BOLD}1. 配置 LLM 模型${NC}"
    echo -e "     登录 Web UI → 系统设置 → 模型管理 → 添加模型"
    echo -e "     支持 30+ 厂商：OpenAI / DeepSeek / 通义千问 / 智谱 / Ollama 等"
    echo ""
    echo -e "  ${BOLD}2. 创建知识库${NC}"
    echo -e "     知识库 → 新建知识库 → 选择分块策略"
    echo -e "     推荐：通用文档用 naive，论文用 paper，表格用 excel"
    echo ""
    echo -e "  ${BOLD}3. 上传文档${NC}"
    echo -e "     知识库 → 上传文档 → 选择文件 → 开始解析"
    echo -e "     支持 PDF/DOCX/PPTX/XLSX/HTML/TXT/MD/图片 等 13+ 种格式"
    echo ""
    echo -e "  ${BOLD}4. 创建对话助手${NC}"
    echo -e "     对话 → 新建对话 → 选择知识库 → 开始问答"
    echo ""
    echo -e "  ${BOLD}5. 常用管理命令${NC}"
    echo -e "     查看状态:   ${0} --status"
    echo -e "     查看日志:   ${0} --logs"
    echo -e "     停止服务:   ${0} --stop"
    echo -e "     重启服务:   ${0} --restart"
    echo -e "     备份数据:   ${0} --backup"
    echo ""
}

# ============================================================================
# 附加功能：停止服务
# ============================================================================
do_stop() {
    log_info "停止 RAGFlow 服务..."
    cd "${INSTALL_DIR}/docker"
    docker compose down
    log_success "所有服务已停止"
}

# ============================================================================
# 附加功能：重启服务
# ============================================================================
do_restart() {
    log_info "重启 RAGFlow 服务..."
    cd "${INSTALL_DIR}/docker"
    docker compose restart
    log_success "所有服务已重启"
}

# ============================================================================
# 附加功能：查看状态
# ============================================================================
do_status() {
    echo ""
    log_banner "RAGFlow 服务状态"
    echo ""
    cd "${INSTALL_DIR}/docker"
    docker compose ps
    echo ""

    log_info "资源使用："
    docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.NetIO}}" \
        $(docker compose ps -q 2>/dev/null) 2>/dev/null || echo "  无法获取"
}

# ============================================================================
# 附加功能：查看日志
# ============================================================================
do_logs() {
    cd "${INSTALL_DIR}/docker"
    log_info "显示实时日志（Ctrl+C 退出）..."
    docker compose logs -f --tail=100
}

# ============================================================================
# 附加功能：备份数据
# ============================================================================
do_backup() {
    log_step "备份 RAGFlow 数据"

    mkdir -p "$BACKUP_DIR"
    local backup_file="${BACKUP_DIR}/ragflow-backup-$(date +%Y%m%d%H%M%S).tar.gz"

    cd "${INSTALL_DIR}/docker"

    log_info "导出 Docker 卷数据..."

    # 备份 .env 和 service_conf
    local temp_dir=$(mktemp -d)
    cp .env "$temp_dir/" 2>/dev/null || true
    cp service_conf.yaml.template "$temp_dir/" 2>/dev/null || true

    # 停止服务以确保数据一致性
    log_info "临时停止服务以确保数据一致性..."
    docker compose stop

    # 创建备份
    tar -czf "$backup_file" \
        -C "${INSTALL_DIR}" docker/.env docker/service_conf.yaml.template \
        2>/dev/null || true

    # 备份 Docker 卷
    for vol in esdata01 mysql_data redis_data minio_data; do
        local vol_name=$(docker volume ls --format '{{.Name}}' | grep "$vol" | head -1)
        if [[ -n "$vol_name" ]]; then
            docker run --rm -v "${vol_name}:/data" -v "${BACKUP_DIR}:/backup" \
                alpine tar -czf "/backup/${vol}-$(date +%Y%m%d%H%M%S).tar.gz" -C /data . 2>/dev/null || true
            log_info "已备份卷: ${vol_name}"
        fi
    done

    # 重启服务
    log_info "重启服务..."
    docker compose start

    log_success "备份完成: ${BACKUP_DIR}"
    echo "  备份文件列表："
    ls -lh "${BACKUP_DIR}"/*.tar.gz 2>/dev/null | tail -10
}

# ============================================================================
# 附加功能：完全卸载
# ============================================================================
do_uninstall() {
    log_step "完全卸载 RAGFlow"

    echo -e "${RED}${BOLD}⚠  警告：此操作将删除所有 RAGFlow 数据，包括：${NC}"
    echo "  - 所有容器"
    echo "  - 所有 Docker 卷（ES、MySQL、Redis、MinIO 数据）"
    echo "  - 所有镜像"
    echo "  - 安装目录"
    echo ""
    read -p "确认卸载？(输入 YES 继续): " confirm

    if [[ "$confirm" != "YES" ]]; then
        log_info "取消卸载"
        return 0
    fi

    cd "${INSTALL_DIR}/docker" 2>/dev/null || true

    log_info "停止并删除容器和卷..."
    docker compose down -v --rmi all 2>/dev/null || true

    log_info "删除安装目录..."
    rm -rf "${INSTALL_DIR}"

    log_success "RAGFlow 已完全卸载"
}

# ============================================================================
# 使用说明
# ============================================================================
show_usage() {
    echo ""
    echo -e "${BOLD}RAGFlow DeepDoc 部署脚本 v${SCRIPT_VERSION}${NC}"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "部署选项:"
    echo "  --gpu                使用 GPU 模式部署（需要 NVIDIA GPU）"
    echo "  --cpu                使用 CPU 模式部署（默认）"
    echo "  --dir <path>         指定安装目录（默认: ~/ragflow）"
    echo "  --version <ver>      指定 RAGFlow 版本（默认: ${RAGFLOW_VERSION}）"
    echo ""
    echo "LLM 配置:"
    echo "  --llm-openai         使用 OpenAI"
    echo "  --llm-deepseek       使用 DeepSeek"
    echo "  --llm-qwen           使用通义千问"
    echo "  --llm-zhipu          使用智谱 AI"
    echo "  --llm-ollama         使用本地 Ollama"
    echo "  --api-key <key>      设置 LLM API Key"
    echo "  --base-url <url>     设置 LLM API 地址"
    echo "  --chat-model <name>  设置对话模型名称"
    echo ""
    echo "管理命令:"
    echo "  --check              仅检查系统环境，不部署"
    echo "  --stop               停止所有服务"
    echo "  --restart            重启所有服务"
    echo "  --status             查看服务状态"
    echo "  --logs               查看实时日志"
    echo "  --backup             备份所有数据"
    echo "  --restore <file>     从备份恢复数据"
    echo "  --uninstall          完全卸载（删除所有数据）"
    echo ""
    echo "其他:"
    echo "  --help               显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0                                    # CPU 模式，默认配置"
    echo "  $0 --gpu                              # GPU 模式"
    echo "  $0 --llm-deepseek --api-key sk-xxx   # 使用 DeepSeek"
    echo "  $0 --llm-ollama                      # 使用本地 Ollama"
    echo "  $0 --dir /opt/ragflow                # 自定义安装目录"
    echo ""
}

# ============================================================================
# 主流程
# ============================================================================
main() {
    echo ""
    echo -e "${MAGENTA}${BOLD}╔══════════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${MAGENTA}${BOLD}║                                                                  ║${NC}"
    echo -e "${MAGENTA}${BOLD}║   🚀  RAGFlow DeepDoc 一键部署脚本 v${SCRIPT_VERSION}                       ║${NC}"
    echo -e "${MAGENTA}${BOLD}║   📦  版本: ${RAGFLOW_VERSION}                                            ║${NC}"
    echo -e "${MAGENTA}${BOLD}║                                                                  ║${NC}"
    echo -e "${MAGENTA}${BOLD}╚══════════════════════════════════════════════════════════════════╝${NC}"
    echo ""

    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --gpu)
                DEVICE="gpu"
                COMPOSE_PROFILES="ragflow-gpu"
                shift
                ;;
            --cpu)
                DEVICE="cpu"
                shift
                ;;
            --dir)
                INSTALL_DIR="$2"
                shift 2
                ;;
            --version)
                RAGFLOW_VERSION="$2"
                RAGFLOW_IMAGE="infiniflow/ragflow:${RAGFLOW_VERSION}"
                shift 2
                ;;
            --llm-openai)
                LLM_FACTORY="OpenAI"
                LLM_BASE_URL="https://api.openai.com/v1"
                LLM_CHAT_MODEL="gpt-4o"
                shift
                ;;
            --llm-deepseek)
                LLM_FACTORY="DeepSeek"
                LLM_BASE_URL="https://api.deepseek.com/v1"
                LLM_CHAT_MODEL="deepseek-chat"
                shift
                ;;
            --llm-qwen)
                LLM_FACTORY="Tongyi-Qianwen"
                LLM_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
                LLM_CHAT_MODEL="qwen-plus"
                shift
                ;;
            --llm-zhipu)
                LLM_FACTORY="ZHIPU-AI"
                LLM_BASE_URL="https://open.bigmodel.cn/api/paas/v4"
                LLM_CHAT_MODEL="glm-4-flash"
                shift
                ;;
            --llm-ollama)
                LLM_FACTORY="Ollama"
                LLM_BASE_URL="http://host.docker.internal:11434/v1"
                LLM_CHAT_MODEL="qwen2.5:7b"
                shift
                ;;
            --api-key)
                LLM_API_KEY="$2"
                shift 2
                ;;
            --base-url)
                LLM_BASE_URL="$2"
                shift 2
                ;;
            --chat-model)
                LLM_CHAT_MODEL="$2"
                shift 2
                ;;
            --check)
                ACTION="check"
                shift
                ;;
            --stop)
                ACTION="stop"
                shift
                ;;
            --restart)
                ACTION="restart"
                shift
                ;;
            --status)
                ACTION="status"
                shift
                ;;
            --logs)
                ACTION="logs"
                shift
                ;;
            --backup)
                ACTION="backup"
                shift
                ;;
            --restore)
                ACTION="restore"
                shift
                ;;
            --uninstall)
                ACTION="uninstall"
                shift
                ;;
            --help)
                show_usage
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                show_usage
                exit 1
                ;;
        esac
    done

    # 执行对应操作
    case "$ACTION" in
        check)
            check_system_requirements
            log_success "环境检查完成，可以部署"
            ;;
        stop)
            do_stop
            ;;
        restart)
            do_restart
            ;;
        status)
            do_status
            ;;
        logs)
            do_logs
            ;;
        backup)
            do_backup
            ;;
        uninstall)
            do_uninstall
            ;;
        deploy)
            log_info "部署模式: ${DEVICE^^}"
            log_info "安装目录: ${INSTALL_DIR}"
            log_info "镜像版本: ${RAGFLOW_IMAGE}"
            [[ -n "$LLM_FACTORY" ]] && log_info "LLM 厂商: ${LLM_FACTORY}"

            check_system_requirements
            configure_system
            setup_gpu
            clone_repository
            generate_env_file
            generate_service_conf
            pull_images
            start_services
            verify_deployment
            show_next_steps

            echo ""
            log_success "🎉 部署流程全部完成！日志已保存到: ${LOG_FILE}"
            echo ""
            ;;
    esac
}

# 执行主流程
main "$@"
