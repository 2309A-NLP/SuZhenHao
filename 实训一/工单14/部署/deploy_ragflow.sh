#!/bin/bash
# ============================================================================
# RAGFlow 一键部署脚本
# 版本：v1.0.0
# 适用环境：Linux / WSL2 Ubuntu
# 项目：RAGFlow DeepDoc 深度文档解析系统
# 生成时间：2026年6月23日
# ============================================================================

set -euo pipefail

# ============================================================================
# 颜色定义
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ============================================================================
# 日志函数
# ============================================================================
log_info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()    { echo -e "\n${CYAN}${BOLD}========== $1 ==========${NC}\n"; }
log_success() { echo -e "${GREEN}${BOLD}✅ $1${NC}"; }

# ============================================================================
# 配置变量（可根据实际环境修改）
# ============================================================================
RAGFLOW_VERSION="v0.23.1"
RAGFLOW_IMAGE="infiniflow/ragflow:${RAGFLOW_VERSION}"
INSTALL_DIR="${HOME}/ragflow"
REPO_URL="https://github.com/infiniflow/ragflow.git"

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

# 密码配置（生产环境请修改！）
MYSQL_PASSWORD="infini_rag_flow"
ES_PASSWORD="infini_rag_flow"
MINIO_USER="rag_flow"
MINIO_PASSWORD="infini_rag_flow"
REDIS_PASSWORD="infini_rag_flow"

# 资源配置
MEM_LIMIT="8073741824"  # 8GB
ES_JAVA_OPTS="-Xms4g -Xmx4g"
DEVICE="cpu"  # cpu 或 gpu

# Embedding 模型配置
TEI_EMBEDDING_MODEL="Qwen/Qwen3-Embedding-0.6B"
COMPOSE_PROFILES=""

# LLM 配置
LLM_FACTORY="OpenAI"
LLM_API_KEY=""
LLM_BASE_URL="https://api.openai.com/v1"
LLM_CHAT_MODEL="gpt-4o"
LLM_EMBEDDING_MODEL=""

# ============================================================================
# 函数：检查系统要求
# ============================================================================
check_system_requirements() {
    log_step "Step 1/8: 检查系统要求"

    # 检查操作系统
    local os_type=$(uname -s)
    log_info "操作系统: ${os_type} $(uname -r)"

    # 检查 CPU 核心数
    local cpu_cores=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo "unknown")
    log_info "CPU 核心数: ${cpu_cores}"
    if [[ "$cpu_cores" -lt 4 ]]; then
        log_warn "CPU 核心数少于 4 个，可能影响性能"
    fi

    # 检查内存
    local total_mem_kb=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}' || echo "0")
    local total_mem_gb=$((total_mem_kb / 1024 / 1024))
    log_info "系统内存: ${total_mem_gb} GB"
    if [[ "$total_mem_gb" -lt 16 ]]; then
        log_warn "系统内存少于 16 GB，建议至少 16 GB"
    fi

    # 检查磁盘空间
    local disk_avail=$(df -BG "${HOME}" 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G' || echo "0")
    log_info "可用磁盘空间: ${disk_avail} GB"
    if [[ "$disk_avail" -lt 50 ]]; then
        log_warn "可用磁盘空间少于 50 GB，建议至少 50 GB"
    fi

    # 检查 Docker
    if ! command -v docker &>/dev/null; then
        log_error "Docker 未安装，请先安装 Docker"
        log_info "安装命令: curl -fsSL https://get.docker.com | sh"
        exit 1
    fi
    local docker_version=$(docker version --format '{{.Server.Version}}' 2>/dev/null || echo "unknown")
    log_info "Docker 版本: ${docker_version}"

    # 检查 Docker Compose
    if docker compose version &>/dev/null; then
        local compose_version=$(docker compose version --short 2>/dev/null || echo "unknown")
        log_info "Docker Compose 版本: ${compose_version}"
    elif command -v docker-compose &>/dev/null; then
        local compose_version=$(docker-compose version --short 2>/dev/null || echo "unknown")
        log_info "Docker Compose (旧版) 版本: ${compose_version}"
        log_warn "建议升级到 Docker Compose V2"
    else
        log_error "Docker Compose 未安装"
        exit 1
    fi

    log_success "系统要求检查通过"
}

# ============================================================================
# 函数：设置系统参数
# ============================================================================
configure_system() {
    log_step "Step 2/8: 配置系统参数"

    # 设置 vm.max_map_count（Elasticsearch 要求）
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
        log_success "vm.max_map_count 已满足要求"
    fi
}

# ============================================================================
# 函数：安装 NVIDIA Container Toolkit（GPU 模式）
# ============================================================================
install_nvidia_toolkit() {
    log_step "Step 3/8: 安装 NVIDIA Container Toolkit（GPU 模式）"

    if [[ "$DEVICE" != "gpu" ]]; then
        log_info "当前为 CPU 模式，跳过 GPU 配置"
        return 0
    fi

    # 检查 NVIDIA 驱动
    if ! command -v nvidia-smi &>/dev/null; then
        log_error "NVIDIA 驱动未安装，请先安装 GPU 驱动"
        exit 1
    fi
    log_info "NVIDIA 驱动版本: $(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)"

    # 检查 nvidia-container-toolkit
    if command -v nvidia-ctk &>/dev/null; then
        log_success "nvidia-container-toolkit 已安装"
        return 0
    fi

    log_info "安装 nvidia-container-toolkit ..."

    # 添加 NVIDIA 仓库
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
        sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
        sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
        sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null

    sudo apt-get update -qq
    sudo apt-get install -y -qq nvidia-container-toolkit

    # 配置 Docker 运行时
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker

    log_success "nvidia-container-toolkit 安装完成"
}

# ============================================================================
# 函数：克隆 RAGFlow 仓库
# ============================================================================
clone_repository() {
    log_step "Step 4/8: 获取 RAGFlow 部署文件"

    if [[ -d "${INSTALL_DIR}" ]]; then
        log_info "安装目录已存在: ${INSTALL_DIR}"
        cd "${INSTALL_DIR}"

        if [[ -d ".git" ]]; then
            log_info "更新仓库 ..."
            git fetch --all 2>/dev/null || true
            git checkout "${RAGFLOW_VERSION}" 2>/dev/null || git pull
        fi
    else
        log_info "克隆 RAGFlow 仓库 ..."
        git clone "${REPO_URL}" "${INSTALL_DIR}"
        cd "${INSTALL_DIR}"
        git checkout "${RAGFLOW_VERSION}" 2>/dev/null || log_warn "使用默认分支"
    fi

    cd docker/
    log_success "仓库准备完成: ${INSTALL_DIR}/docker"
}

# ============================================================================
# 函数：生成环境配置文件
# ============================================================================
generate_env_file() {
    log_step "Step 5/8: 生成环境配置文件"

    local env_file="${INSTALL_DIR}/docker/.env"

    # 备份已有配置
    if [[ -f "$env_file" ]]; then
        cp "$env_file" "${env_file}.bak.$(date +%Y%m%d%H%M%S)"
        log_info "已备份原有 .env 文件"
    fi

    cat > "$env_file" << EOF
# ============================================================================
# RAGFlow 环境配置文件
# 生成时间：$(date '+%Y-%m-%d %H:%M:%S')
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
# 密码配置（生产环境务必修改！）
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
# 函数：生成服务配置文件
# ============================================================================
generate_service_conf() {
    log_step "Step 6/8: 生成服务配置文件"

    local conf_file="${INSTALL_DIR}/docker/service_conf.yaml.template"

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
  factory: '${LLM_FACTORY}'
  api_key: '${LLM_API_KEY}'
  base_url: '${LLM_BASE_URL}'
  default_models:
    chat_model:
      name: '${LLM_CHAT_MODEL}'
      factory: '${LLM_FACTORY}'
      api_key: '${LLM_API_KEY}'
      base_url: '${LLM_BASE_URL}'
    embedding_model:
      api_key: '${LLM_API_KEY}'
      base_url: 'http://tei:80'
    rerank_model: 'bge-reranker-v2-m3'
    image2text_model: ''
    asr_model: ''
EOF

    log_success "服务配置文件已生成: ${conf_file}"
}

# ============================================================================
# 函数：启动服务
# ============================================================================
start_services() {
    log_step "Step 7/8: 启动 RAGFlow 服务"

    cd "${INSTALL_DIR}/docker"

    # 拉取镜像
    log_info "拉取 Docker 镜像 ..."
    if [[ "$DEVICE" == "gpu" ]]; then
        docker compose --profile ragflow-gpu -f docker-compose.yml pull
    else
        docker compose -f docker-compose.yml pull
    fi

    # 启动服务
    log_info "启动所有服务 ..."
    if [[ "$DEVICE" == "gpu" ]]; then
        docker compose --profile ragflow-gpu -f docker-compose.yml up -d
    else
        docker compose -f docker-compose.yml up -d
    fi

    log_success "服务启动命令已执行"
}

# ============================================================================
# 函数：验证部署
# ============================================================================
verify_deployment() {
    log_step "Step 8/8: 验证部署状态"

    cd "${INSTALL_DIR}/docker"

    # 等待服务启动
    log_info "等待服务启动（最多 120 秒）..."
    local max_wait=120
    local elapsed=0

    while [[ $elapsed -lt $max_wait ]]; do
        local unhealthy=$(docker compose ps --format json 2>/dev/null | grep -c '"unhealthy"' || echo "0")
        local running=$(docker compose ps --format json 2>/dev/null | grep -c '"running"' || echo "0")

        if [[ "$running" -gt 0 && "$unhealthy" -eq 0 ]]; then
            break
        fi

        sleep 5
        elapsed=$((elapsed + 5))
        echo -n "."
    done
    echo ""

    # 显示容器状态
    log_info "容器运行状态："
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

    for svc in "${services[@]}"; do
        local name="${svc%%:*}"
        local port="${svc##*:}"
        if ss -tlnp 2>/dev/null | grep -q ":${port} " || netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
            echo -e "  ${GREEN}✓${NC} ${name} (端口 ${port}) - ${GREEN}运行中${NC}"
        else
            echo -e "  ${RED}✗${NC} ${name} (端口 ${port}) - ${RED}未监听${NC}"
        fi
    done

    # 检查 Elasticsearch 健康状态
    echo ""
    log_info "Elasticsearch 健康检查："
    local es_health=$(curl -s -u "elastic:${ES_PASSWORD}" "http://localhost:${ES_PORT}/_cluster/health?pretty" 2>/dev/null || echo "无法连接")
    echo "$es_health" | head -5

    # 输出访问地址
    echo ""
    echo -e "${GREEN}${BOLD}============================================================================${NC}"
    echo -e "${GREEN}${BOLD}  RAGFlow 部署完成！${NC}"
    echo -e "${GREEN}${BOLD}============================================================================${NC}"
    echo ""
    echo -e "  ${BOLD}Web UI 访问地址:${NC}     http://localhost:${WEB_HTTP_PORT}"
    echo -e "  ${BOLD}API 服务地址:${NC}        http://localhost:${API_PORT}"
    echo -e "  ${BOLD}管理后台地址:${NC}        http://localhost:${ADMIN_PORT}"
    echo -e "  ${BOLD}MinIO 控制台:${NC}        http://localhost:${MINIO_CONSOLE_PORT}"
    echo ""
    echo -e "  ${BOLD}默认管理员账号:${NC}      admin"
    echo -e "  ${BOLD}默认管理员密码:${NC}      admin"
    echo ""
    echo -e "  ${YELLOW}⚠ 请务必修改默认密码！${NC}"
    echo -e "  ${YELLOW}⚠ 生产环境请修改 .env 中的所有密码配置！${NC}"
    echo ""
    echo -e "${GREEN}${BOLD}============================================================================${NC}"
}

# ============================================================================
# 函数：显示使用说明
# ============================================================================
show_usage() {
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --gpu           使用 GPU 模式部署（需要 NVIDIA GPU）"
    echo "  --cpu           使用 CPU 模式部署（默认）"
    echo "  --dir <path>    指定安装目录（默认: ~/ragflow）"
    echo "  --version <ver> 指定 RAGFlow 版本（默认: ${RAGFLOW_VERSION}）"
    echo "  --help          显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0                    # CPU 模式，默认配置"
    echo "  $0 --gpu              # GPU 模式"
    echo "  $0 --dir /opt/ragflow # 自定义安装目录"
    echo ""
}

# ============================================================================
# 主流程
# ============================================================================
main() {
    echo ""
    echo -e "${CYAN}${BOLD}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}${BOLD}║         RAGFlow DeepDoc 一键部署脚本                        ║${NC}"
    echo -e "${CYAN}${BOLD}║         版本: ${RAGFLOW_VERSION}                                     ║${NC}"
    echo -e "${CYAN}${BOLD}╚══════════════════════════════════════════════════════════════╝${NC}"
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

    log_info "部署模式: ${DEVICE^^}"
    log_info "安装目录: ${INSTALL_DIR}"
    log_info "镜像版本: ${RAGFLOW_IMAGE}"

    # 执行部署流程
    check_system_requirements
    configure_system
    install_nvidia_toolkit
    clone_repository
    generate_env_file
    generate_service_conf
    start_services
    verify_deployment

    echo ""
    log_success "部署流程全部完成！"
    echo ""
}

# 执行主流程
main "$@"
