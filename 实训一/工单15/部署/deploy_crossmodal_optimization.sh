#!/bin/bash
# ============================================================================
# RAGFlow 跨模态检索优化系统 一键部署脚本 v2.0
# 版本：v2.0.0
# 适用环境：Linux / WSL2 Ubuntu
# 项目：工单15 — 技术图纸与文本的跨模态检索优化
# 生成时间：2026年6月23日
# ============================================================================
#
# 使用方法：
#   chmod +x deploy_crossmodal_optimization.sh
#   ./deploy_crossmodal_optimization.sh                    # 默认配置部署
#   ./deploy_crossmodal_optimization.sh --gpu              # GPU 模式
#   ./deploy_crossmodal_optimization.sh --check            # 仅检查环境
#   ./deploy_crossmodal_optimization.sh --status           # 查看服务状态
#   ./deploy_crossmodal_optimization.sh --logs             # 查看实时日志
#   ./deploy_crossmodal_optimization.sh --stop             # 停止服务
#   ./deploy_crossmodal_optimization.sh --restart          # 重启服务
#   ./deploy_crossmodal_optimization.sh --backup           # 备份数据
#   ./deploy_crossmodal_optimization.sh --uninstall        # 完全卸载
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
API_PORT=9380
ADMIN_PORT=9381
ES_PORT=1200
MYSQL_PORT=5455
MINIO_API_PORT=9003
MINIO_CONSOLE_PORT=9004
REDIS_PORT=6379

# 密码配置
MYSQL_PASSWORD=""
ES_PASSWORD=""
MINIO_USER="rag_flow"
MINIO_PASSWORD=""
REDIS_PASSWORD=""

# 资源配置
MEM_LIMIT="8073741824"
DEVICE="cpu"

# LLM 配置
LLM_FACTORY="Ollama"
LLM_BASE_URL="http://host.docker.internal:11434/v1"
LLM_CHAT_MODEL="deepseek-r1:7b"
LLM_EMBEDDING_MODEL="bge-m3:latest"
RERANK_MODEL="gte-rerank@Tongyi-Qianwen"

# 操作模式
ACTION="deploy"

# ============================================================================
# 颜色与日志
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

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
generate_password() {
    openssl rand -base64 32 | tr -dc 'a-zA-Z0-9!@#$%^&*' | head -c "${1:-16}"
}

check_port() {
    local port=$1 service=$2
    if ss -tlnp 2>/dev/null | grep -q ":${port} " || netstat -tlnp 2>/dev/null | grep -q ":${port} "; then
        log_warn "端口 ${port} 已被占用（${service}）"
        return 1
    fi
    return 0
}

save_credentials() {
    local cred_file="${INSTALL_DIR}/docker/.credentials"
    cat > "$cred_file" << EOF
# RAGFlow 凭据文件
# 生成时间：$(date '+%Y-%m-%d %H:%M:%S')
MySQL:     ${MYSQL_PASSWORD}
ES:        ${ES_PASSWORD}
MinIO:     ${MINIO_USER} / ${MINIO_PASSWORD}
Redis:     ${REDIS_PASSWORD}
Web UI:    http://localhost:${WEB_HTTP_PORT}
Admin:     admin / admin（请首次登录后修改！）
EOF
    chmod 600 "$cred_file"
}

# ============================================================================
# Step 1: 检查系统要求
# ============================================================================
check_system_requirements() {
    log_step "1/10 — 检查系统要求"

    log_info "操作系统: $(uname -s) $(uname -r)"
    local cpu_cores=$(nproc 2>/dev/null || echo "unknown")
    log_info "CPU 核心数: ${cpu_cores}"
    [[ "$cpu_cores" -lt 4 ]] && log_warn "CPU 核心数少于 4，可能影响性能"

    local total_mem_gb=$(($(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}') / 1024 / 1024))
    log_info "系统内存: ${total_mem_gb} GB"
    [[ "$total_mem_gb" -lt 16 ]] && log_warn "内存少于 16 GB，建议至少 16 GB"

    local disk_avail=$(df -BG "${HOME}" 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G')
    log_info "可用磁盘: ${disk_avail} GB"
    [[ "$disk_avail" -lt 50 ]] && log_warn "磁盘少于 50 GB"

    if ! command -v docker &>/dev/null; then
        log_error "Docker 未安装！请执行: curl -fsSL https://get.docker.com | sh"
        exit 1
    fi
    log_info "Docker: $(docker version --format '{{.Server.Version}}' 2>/dev/null || echo unknown)"

    if ! docker compose version &>/dev/null; then
        log_error "Docker Compose 未安装！"
        exit 1
    fi

    if ! docker info &>/dev/null; then
        log_error "Docker 守护进程未运行！请执行: sudo systemctl start docker"
        exit 1
    fi

    command -v git &>/dev/null || { sudo apt-get update -qq && sudo apt-get install -y -qq git; }

    log_info "检查关键端口..."
    check_port "$WEB_HTTP_PORT" "Web UI" || true
    check_port "$API_PORT" "API" || true
    check_port "$ES_PORT" "ES" || true
    check_port "$MYSQL_PORT" "MySQL" || true
    check_port "$REDIS_PORT" "Redis" || true
    check_port "$MINIO_API_PORT" "MinIO" || true

    log_success "系统要求检查完成"
}

# ============================================================================
# Step 2: 配置系统参数
# ============================================================================
configure_system() {
    log_step "2/10 — 配置系统参数"
    local current_val=$(sysctl -n vm.max_map_count 2>/dev/null || echo "0")
    if [[ "$current_val" -lt 262144 ]]; then
        sudo sysctl -w vm.max_map_count=262144
        grep -q "vm.max_map_count=262144" /etc/sysctl.conf 2>/dev/null || \
            echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf > /dev/null
        log_success "vm.max_map_count 已设置为 262144"
    else
        log_success "vm.max_map_count 已满足要求"
    fi
}

# ============================================================================
# Step 3: GPU 配置
# ============================================================================
setup_gpu() {
    log_step "3/10 — GPU 配置"
    if [[ "$DEVICE" != "gpu" ]]; then
        log_info "CPU 模式，跳过 GPU 配置"
        return 0
    fi

    if ! command -v nvidia-smi &>/dev/null; then
        log_error "NVIDIA 驱动未安装！"
        exit 1
    fi
    log_info "GPU: $(nvidia-smi --query-gpu=name,driver_version --format=csv,noheader 2>/dev/null | head -1)"

    if command -v nvidia-ctk &>/dev/null; then
        log_success "nvidia-container-toolkit 已安装"
    else
        log_info "安装 nvidia-container-toolkit..."
        curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | \
            sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
        curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
            sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
            sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list > /dev/null
        sudo apt-get update -qq
        sudo apt-get install -y -qq nvidia-container-toolkit
        sudo nvidia-ctk runtime configure --runtime=docker
        sudo systemctl restart docker
        log_success "nvidia-container-toolkit 安装完成"
    fi
}

# ============================================================================
# Step 4: 获取 RAGFlow 部署文件
# ============================================================================
clone_repository() {
    log_step "4/10 — 获取 RAGFlow 部署文件"
    if [[ -d "${INSTALL_DIR}/.git" ]]; then
        cd "${INSTALL_DIR}"
        git fetch --all --tags 2>/dev/null || true
        git checkout "$RAGFLOW_VERSION" 2>/dev/null || true
        log_info "已更新到版本 ${RAGFLOW_VERSION}"
    elif [[ ! -d "${INSTALL_DIR}" ]]; then
        git clone --depth 1 "$REPO_URL" "${INSTALL_DIR}"
        cd "${INSTALL_DIR}"
        git checkout "$RAGFLOW_VERSION" 2>/dev/null || true
    fi
    cd "${INSTALL_DIR}/docker"
    log_success "仓库准备完成"
}

# ============================================================================
# Step 5: 生成环境配置
# ============================================================================
generate_env_file() {
    log_step "5/10 — 生成环境配置"
    [[ -z "$MYSQL_PASSWORD" ]] && MYSQL_PASSWORD=$(generate_password 16)
    [[ -z "$ES_PASSWORD" ]] && ES_PASSWORD=$(generate_password 16)
    [[ -z "$MINIO_PASSWORD" ]] && MINIO_PASSWORD=$(generate_password 16)
    [[ -z "$REDIS_PASSWORD" ]] && REDIS_PASSWORD=$(generate_password 16)

    local env_file="${INSTALL_DIR}/docker/.env"
    [[ -f "$env_file" ]] && cp "$env_file" "${env_file}.bak.$(date +%s)"

    cat > "$env_file" << EOF
RAGFLOW_IMAGE=${RAGFLOW_IMAGE}
DEVICE=${DEVICE}
DOC_ENGINE=elasticsearch
MEM_LIMIT=${MEM_LIMIT}
TZ=Asia/Shanghai
SVR_WEB_HTTP_PORT=${WEB_HTTP_PORT}
SVR_HTTP_PORT=${API_PORT}
ADMIN_SVR_HTTP_PORT=${ADMIN_PORT}
SVR_ES_PORT=${ES_PORT}
SVR_MYSQL_PORT=${MYSQL_PORT}
MINIO_PORT=${MINIO_API_PORT}
MINIO_CONSOLE_PORT=${MINIO_CONSOLE_PORT}
SVR_REDIS_PORT=${REDIS_PORT}
MYSQL_PASSWORD=${MYSQL_PASSWORD}
ES_PASSWORD=${ES_PASSWORD}
MINIO_USER=${MINIO_USER}
MINIO_PASSWORD=${MINIO_PASSWORD}
REDIS_PASSWORD=${REDIS_PASSWORD}
REGISTER_ENABLED=1
EOF
    log_success "环境配置已生成"
}

# ============================================================================
# Step 6: 生成服务配置
# ============================================================================
generate_service_conf() {
    log_step "6/10 — 生成服务配置"
    cat > "${INSTALL_DIR}/docker/service_conf.yaml.template" << EOF
es:
  hosts: http://es01:9200
  username: elastic
  password: ${ES_PASSWORD}
mysql:
  host: mysql
  port: 3306
  user: root
  password: ${MYSQL_PASSWORD}
  database: rag_flow
redis:
  host: redis
  port: 6379
  password: ${REDIS_PASSWORD}
minio:
  host: minio
  port: 9000
  user: ${MINIO_USER}
  password: ${MINIO_PASSWORD}
user_default_llm:
  factory: '${LLM_FACTORY}'
  api_key: '***'
  base_url: '${LLM_BASE_URL}'
  default_models:
    chat_model:
      name: '${LLM_CHAT_MODEL}'
      factory: '${LLM_FACTORY}'
      api_key: '***'
      base_url: '${LLM_BASE_URL}'
    embedding_model:
      name: '${LLM_EMBEDDING_MODEL}'
      api_key: '***'
      base_url: '${LLM_BASE_URL}'
    rerank_model: '${RERANK_MODEL}'
EOF
    log_success "服务配置已生成"
}

# ============================================================================
# Step 7: 部署优化代码
# ============================================================================
deploy_optimization_code() {
    log_step "7/10 — 部署跨模态检索优化代码"

    local src_dir="${INSTALL_DIR}"

    # 备份原始文件
    local backup_ts=$(date +%s)
    for f in rag/nlp/query.py rag/nlp/search.py; do
        if [[ -f "${src_dir}/${f}" ]]; then
            cp "${src_dir}/${f}" "${src_dir}/${f}.bak.${backup_ts}"
            log_info "已备份: ${f}"
        fi
    done

    # 复制优化后的文件
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    if [[ -f "${SCRIPT_DIR}/optimized_query.py" ]]; then
        cp "${SCRIPT_DIR}/optimized_query.py" "${src_dir}/rag/nlp/query.py"
        log_info "已部署: optimized_query.py → rag/nlp/query.py"
    else
        log_warn "未找到 optimized_query.py，跳过查询理解增强模块"
    fi

    if [[ -f "${SCRIPT_DIR}/optimized_search.py" ]]; then
        cp "${SCRIPT_DIR}/optimized_search.py" "${src_dir}/rag/nlp/search.py"
        log_info "已部署: optimized_search.py → rag/nlp/search.py"
    else
        log_warn "未找到 optimized_search.py，跳过混合检索策略模块"
    fi

    log_success "优化代码部署完成"
}

# ============================================================================
# Step 8: 拉取镜像
# ============================================================================
pull_images() {
    log_step "8/10 — 拉取 Docker 镜像"
    cd "${INSTALL_DIR}/docker"
    if [[ "$DEVICE" == "gpu" ]]; then
        docker compose --profile ragflow-gpu -f docker-compose.yml pull 2>&1 | tail -5
    else
        docker compose -f docker-compose.yml pull 2>&1 | tail -5
    fi
    log_success "镜像拉取完成"
}

# ============================================================================
# Step 9: 启动服务
# ============================================================================
start_services() {
    log_step "9/10 — 启动 RAGFlow 服务"
    cd "${INSTALL_DIR}/docker"
    if [[ "$DEVICE" == "gpu" ]]; then
        docker compose --profile ragflow-gpu -f docker-compose.yml up -d
    else
        docker compose -f docker-compose.yml up -d
    fi
    log_success "服务启动完成"
}

# ============================================================================
# Step 10: 验证部署
# ============================================================================
verify_deployment() {
    log_step "10/10 — 验证部署状态"
    cd "${INSTALL_DIR}/docker"

    log_info "等待服务启动（最多 180 秒）..."
    local elapsed=0
    while [[ $elapsed -lt 180 ]]; do
        local running=$(docker compose ps --format json 2>/dev/null | grep -c '"running"' || echo 0)
        if [[ "$running" -gt 0 ]]; then break; fi
        sleep 5
        elapsed=$((elapsed + 5))
        echo -n "."
    done
    echo ""

    log_info "容器状态："
    docker compose ps 2>/dev/null || true

    echo ""
    log_info "端口检查："
    for svc in "Web UI:${WEB_HTTP_PORT}" "API:${API_PORT}" "ES:${ES_PORT}" "MySQL:${MYSQL_PORT}" "Redis:${REDIS_PORT}" "MinIO:${MINIO_API_PORT}"; do
        local name="${svc%%:*}" port="${svc##*:}"
        if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
            echo -e "  ${GREEN}✓${NC} ${name} (${port})"
        else
            echo -e "  ${RED}✗${NC} ${name} (${port})"
        fi
    done

    save_credentials

    echo ""
    log_banner "╔══════════════════════════════════════════════════════════════╗"
    log_banner "║     🎉 RAGFlow 跨模态检索优化系统 部署完成！                 ║"
    log_banner "╚══════════════════════════════════════════════════════════════╝"
    echo ""
    echo -e "  ${BOLD}📌 访问地址:${NC} http://localhost:${WEB_HTTP_PORT}"
    echo -e "  ${BOLD}📌 管理员:${NC} admin / admin（请首次登录后修改！）"
    echo -e "  ${BOLD}📌 凭据文件:${NC} ${INSTALL_DIR}/docker/.credentials"
    echo ""
    echo -e "  ${BOLD}📌 部署后配置步骤:${NC}"
    echo -e "  1. 登录 Web UI → 系统设置 → 添加 LLM 模型"
    echo -e "     - Chat: ${LLM_CHAT_MODEL}@${LLM_FACTORY}"
    echo -e "     - Embedding: ${LLM_EMBEDDING_MODEL}@${LLM_FACTORY}"
    echo -e "     - Rerank: ${RERANK_MODEL}"
    echo -e "  2. 创建知识库 → 上传专利文档 → 设置解析参数："
    echo -e "     - chunk_token_num: 512"
    echo -e "     - overlapped_percent: 0.2"
    echo -e "     - image_table_context_window: 2"
    echo -e "     - mineru_lang: Chinese"
    echo -e "  3. 创建助手 → 关联知识库 → 设置检索参数："
    echo -e "     - similarity_threshold: 0.1"
    echo -e "     - vector_similarity_weight: 0.5"
    echo -e "     - top_n: 10"
    echo -e "     - rerank_id: ${RERANK_MODEL}"
    echo -e "  4. 替换系统提示词（参考 optimized_prompt.py）"
    echo ""
}

# ============================================================================
# 附加功能
# ============================================================================
do_stop()    { cd "${INSTALL_DIR}/docker" && docker compose down && log_success "已停止"; }
do_restart() { cd "${INSTALL_DIR}/docker" && docker compose restart && log_success "已重启"; }
do_status()  { cd "${INSTALL_DIR}/docker" && docker compose ps; }
do_logs()    { cd "${INSTALL_DIR}/docker" && docker compose logs -f --tail=100; }

do_backup() {
    mkdir -p "$BACKUP_DIR"
    cd "${INSTALL_DIR}/docker"
    docker compose stop
    local bf="${BACKUP_DIR}/ragflow-$(date +%Y%m%d%H%M%S).tar.gz"
    tar -czf "$bf" .env service_conf.yaml.template 2>/dev/null || true
    for vol in esdata01 mysql_data redis_data minio_data; do
        local vn=$(docker volume ls --format '{{.Name}}' | grep "$vol" | head -1)
        [[ -n "$vn" ]] && docker run --rm -v "${vn}:/data" -v "${BACKUP_DIR}:/backup" \
            alpine tar -czf "/backup/${vol}-$(date +%s).tar.gz" -C /data . 2>/dev/null || true
    done
    docker compose start
    log_success "备份完成: ${BACKUP_DIR}"
}

do_uninstall() {
    read -p "确认卸载？(输入 YES): " confirm
    [[ "$confirm" != "YES" ]] && return
    cd "${INSTALL_DIR}/docker" && docker compose down -v --rmi all 2>/dev/null
    rm -rf "${INSTALL_DIR}"
    log_success "已完全卸载"
}

show_usage() {
    echo "用法: $0 [--gpu|--cpu|--check|--stop|--restart|--status|--logs|--backup|--uninstall|--help]"
}

# ============================================================================
# 主流程
# ============================================================================
main() {
    echo ""
    log_banner "╔══════════════════════════════════════════════════════════════════╗"
    log_banner "║   🚀 RAGFlow 跨模态检索优化系统 部署脚本 v${SCRIPT_VERSION}                 ║"
    log_banner "║   📦 RAGFlow ${RAGFLOW_VERSION} + 工单15 优化模块                           ║"
    log_banner "╚══════════════════════════════════════════════════════════════════╝"
    echo ""

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --gpu) DEVICE="gpu"; shift ;;
            --cpu) DEVICE="cpu"; shift ;;
            --dir) INSTALL_DIR="$2"; shift 2 ;;
            --check) ACTION="check"; shift ;;
            --stop) ACTION="stop"; shift ;;
            --restart) ACTION="restart"; shift ;;
            --status) ACTION="status"; shift ;;
            --logs) ACTION="logs"; shift ;;
            --backup) ACTION="backup"; shift ;;
            --uninstall) ACTION="uninstall"; shift ;;
            --help) show_usage; exit 0 ;;
            *) log_error "未知选项: $1"; show_usage; exit 1 ;;
        esac
    done

    case "$ACTION" in
        check) check_system_requirements ;;
        stop) do_stop ;;
        restart) do_restart ;;
        status) do_status ;;
        logs) do_logs ;;
        backup) do_backup ;;
        uninstall) do_uninstall ;;
        deploy)
            log_info "部署模式: ${DEVICE^^}"
            check_system_requirements
            configure_system
            setup_gpu
            clone_repository
            generate_env_file
            generate_service_conf
            deploy_optimization_code
            pull_images
            start_services
            verify_deployment
            log_success "🎉 全部完成！日志: ${LOG_FILE}"
            ;;
    esac
}

main "$@"
