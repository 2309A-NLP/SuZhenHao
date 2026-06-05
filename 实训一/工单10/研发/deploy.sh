#!/bin/bash
# ============================================================
# 招股说明书智能问答系统（Docker 版） - 一键部署脚本
# 支持两种部署方式: Docker / 传统部署
# 适用环境: Ubuntu 20.04+ / CentOS 7+ / Debian 11+
# 使用方式: chmod +x deploy.sh && sudo ./deploy.sh
# ============================================================

set -euo pipefail

# ======================== 配置区 ========================
APP_NAME="rag-qa-system"
APP_USER="ragapp"
APP_DIR="/opt/${APP_NAME}"
PYTHON_VERSION="3.10"
VENV_DIR="${APP_DIR}/venv"
DATA_DIR="${APP_DIR}/data"
IMAGE_DIR="${APP_DIR}/data/images"
LOG_DIR="/var/log/${APP_NAME}"
SERVICE_NAME="${APP_NAME}"
PORT=8080
STREAMLIT_PORT=8501

# 部署方式: docker / traditional（默认 docker）
DEPLOY_MODE="${DEPLOY_MODE:-docker}"

# Docker 镜像名
DOCKER_IMAGE="rag-qa-system:latest"
DOCKER_CONTAINER="rag-qa"

# API 配置
DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-***}"
DEEPSEEK_API_BASE="${DEEPSEEK_API_BASE:-https://api.deepseek.com}"
QWEN_VL_API_KEY="${QWEN_VL_API_KEY:-***}"
QWEN_VL_API_BASE="${QWEN_VL_API_BASE:-https://dashscope.aliyuncs.com/compatible-mode/v1}"

# 检索模式: vector / bm25 / hybrid
RETRIEVAL_MODE="${RETRIEVAL_MODE:-hybrid}"

# HuggingFace 镜像
HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"

# 颜色
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}━━━ $* ━━━${NC}"; }

check_root() { [[ $EUID -ne 0 ]] && { log_error "请用 root 运行: sudo ./deploy.sh"; exit 1; }; }
detect_os() {
    if [[ -f /etc/os-release ]]; then . /etc/os-release; OS=$ID; OS_VERSION=$VERSION_ID
    elif [[ -f /etc/centos-release ]]; then OS="centos"
    else log_error "不支持的操作系统"; exit 1; fi
    log_info "系统: ${OS} ${OS_VERSION}"
}

# ======================== Docker 部署 ========================
deploy_docker() {
    log_step "Docker 部署模式"

    # 检查 Docker
    if ! command -v docker &>/dev/null; then
        log_info "安装 Docker..."
        case $OS in
            ubuntu|debian)
                apt-get update -qq
                apt-get install -y -qq docker.io docker-compose-v2
                ;;
            centos|rhel|rocky|almalinux)
                yum install -y docker docker-compose || dnf install -y docker docker-compose
                ;;
        esac
        systemctl enable docker; systemctl start docker
    fi
    log_info "Docker: $(docker --version 2>&1)"

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # 构建镜像
    log_info "构建 Docker 镜像（含 CPU PyTorch + 全部依赖）..."
    docker build -t ${DOCKER_IMAGE} \
        --build-arg HF_ENDPOINT=${HF_ENDPOINT} \
        "${SCRIPT_DIR}"
    log_info "镜像构建完成: ${DOCKER_IMAGE}"

    # 停止旧容器
    docker rm -f ${DOCKER_CONTAINER} 2>/dev/null || true

    # 创建 .env 文件
    cat > "${SCRIPT_DIR}/.env.docker" << EOF
DEEPSEEK_API_KEY=***
DEEPSEEK_API_BASE=${DEEPSEEK_API_BASE}
QWEN_VL_API_KEY=***
QWEN_VL_API_BASE=${QWEN_VL_API_BASE}
QWEN_VL_MODEL=qwen-vl-plus-latest
RETRIEVAL_MODE=${RETRIEVAL_MODE}
HF_ENDPOINT=${HF_ENDPOINT}
EOF

    # 运行容器
    log_info "启动 Docker 容器..."
    docker run -d \
        --name ${DOCKER_CONTAINER} \
        --restart unless-stopped \
        -p ${PORT}:8080 \
        --env-file "${SCRIPT_DIR}/.env.docker" \
        -v "${SCRIPT_DIR}/data:/app/data" \
        -v "${SCRIPT_DIR}/data/images:/app/data/images" \
        --memory=4g \
        --cpus=2 \
        ${DOCKER_IMAGE}

    sleep 5
    docker ps | grep -q ${DOCKER_CONTAINER} && log_info "✅ 容器运行正常" || log_error "容器启动失败"

    # 拷贝 PDF 到数据目录
    for pdf in "${SCRIPT_DIR}"/*.pdf "${SCRIPT_DIR}/data/"*.pdf; do
        [[ -f "$pdf" ]] && docker cp "$pdf" "${DOCKER_CONTAINER}:/app/data/" && log_info "PDF: $(basename "$pdf")"
    done

    # 验证
    log_info "等待服务初始化..."
    sleep 10
    curl -sf http://localhost:${PORT}/api/health >/dev/null 2>&1 && log_info "✅ 健康检查通过" || log_warn "API 还在初始化"
}

# ======================== 传统部署 ========================
deploy_traditional() {
    log_step "传统部署模式"

    # Step 1: 系统依赖
    log_step "Step 1/9: 安装系统依赖"
    case $OS in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq python${PYTHON_VERSION} python${PYTHON_VERSION}-venv \
                python${PYTHON_VERSION}-dev python3-pip build-essential \
                libgl1-mesa-glx libglib2.0-0 libjpeg-dev libpng-dev curl wget git 2>/dev/null || {
                    apt-get install -y -qq software-properties-common
                    add-apt-repository -y ppa:deadsnakes/ppa; apt-get update -qq
                    apt-get install -y -qq python${PYTHON_VERSION} python${PYTHON_VERSION}-venv
                }
            ;;
        centos|rhel|rocky|almalinux)
            yum install -y epel-release || true
            yum install -y python3 python3-devel python3-pip gcc gcc-c++ make \
                mesa-libGL glib2 libjpeg-turbo-devel libpng-devel curl wget git
            ;;
        *) log_error "不支持: ${OS}"; exit 1 ;;
    esac
    PYTHON_CMD="python${PYTHON_VERSION}"; command -v $PYTHON_CMD &>/dev/null || PYTHON_CMD="python3"
    log_info "Python: $($PYTHON_CMD --version 2>&1)"

    # Step 2: 用户和目录
    log_step "Step 2/9: 创建用户和目录"
    id -u $APP_USER &>/dev/null || useradd --system --shell /bin/false --home-dir $APP_DIR --create-home $APP_USER
    mkdir -p $APP_DIR $DATA_DIR $DATA_DIR/faiss_index $IMAGE_DIR $LOG_DIR

    # Step 3: 部署代码
    log_step "Step 3/9: 部署应用代码"
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cp -r "${SCRIPT_DIR}/"* "${APP_DIR}/" 2>/dev/null || true
    cp -r "${SCRIPT_DIR}"/.* "${APP_DIR}/" 2>/dev/null || true
    for pdf in "${SCRIPT_DIR}"/*.pdf "${SCRIPT_DIR}/data/"*.pdf; do
        [[ -f "$pdf" ]] && cp "$pdf" "${DATA_DIR}/" && log_info "PDF: $(basename "$pdf")"
    done
    chown -R ${APP_USER}:${APP_USER} ${APP_DIR} ${LOG_DIR}; chmod -R 755 ${APP_DIR}

    # Step 4: 虚拟环境
    log_step "Step 4/9: 配置虚拟环境"
    export HF_ENDPOINT=${HF_ENDPOINT}
    $PYTHON_CMD -m venv $VENV_DIR; source ${VENV_DIR}/bin/activate
    pip install --upgrade pip setuptools wheel -q
    pip install torch --index-url https://download.pytorch.org/whl/cpu -q 2>/dev/null || pip install torch -q
    [[ -f "${APP_DIR}/requirements.txt" ]] && pip install -r "${APP_DIR}/requirements.txt" -q
    pip install gunicorn -q; deactivate

    # Step 5: 环境变量
    log_step "Step 5/9: 配置环境变量"
    cat > "${APP_DIR}/.env" << EOF
DEEPSEEK_API_KEY=***
DEEPSEEK_API_BASE=${DEEPSEEK_API_BASE}
QWEN_VL_API_KEY=***
QWEN_VL_API_BASE=${QWEN_VL_API_BASE}
QWEN_VL_MODEL=qwen-vl-plus-latest
PDF_DIR=${DATA_DIR}
RETRIEVAL_MODE=${RETRIEVAL_MODE}
IMAGE_DIR=${IMAGE_DIR}
MAX_IMAGE_SIZE_MB=10
HF_ENDPOINT=${HF_ENDPOINT}
DEBUG=False
ENVIRONMENT=production
API_PORT=${PORT}
STREAMLIT_PORT=${STREAMLIT_PORT}
EOF
    chown ${APP_USER}:${APP_USER} "${APP_DIR}/.env"; chmod 600 "${APP_DIR}/.env"

    # Step 6: 更新配置
    log_step "Step 6/9: 更新配置路径"
    sed -i "s|PDF_DIR = .*|PDF_DIR = \"${DATA_DIR}\"|g" "${APP_DIR}/config.py"
    sed -i "s|FAISS_INDEX_PATH = .*|FAISS_INDEX_PATH = \"${DATA_DIR}/faiss_index\"|g" "${APP_DIR}/config.py"
    sed -i "s|IMAGE_DIR = .*|IMAGE_DIR = \"${IMAGE_DIR}\"|g" "${APP_DIR}/config.py"

    # Step 7: Systemd
    log_step "Step 7/9: 配置 Systemd 服务"
    cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=RAG 问答系统（Docker 版） - API
After=network.target
[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin"
Environment="HF_ENDPOINT=${HF_ENDPOINT}"
EnvironmentFile=${APP_DIR}/.env
ExecStart=${VENV_DIR}/bin/uvicorn api_server:app --host 0.0.0.0 --port ${PORT} --workers 2 --log-level info
Restart=always
RestartSec=5
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${APP_DIR}/data ${LOG_DIR}
PrivateTmp=yes
LimitNOFILE=65536
MemoryMax=4G
StandardOutput=append:${LOG_DIR}/api.log
StandardError=append:${LOG_DIR}/api-error.log
[Install]
WantedBy=multi-user.target
EOF

    cat > /etc/systemd/system/${SERVICE_NAME}-streamlit.service << EOF
[Unit]
Description=RAG 问答系统 - Streamlit UI
After=network.target ${SERVICE_NAME}.service
[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin"
Environment="HF_ENDPOINT=${HF_ENDPOINT}"
EnvironmentFile=${APP_DIR}/.env
ExecStart=${VENV_DIR}/bin/streamlit run ui_app.py --server.port ${STREAMLIT_PORT} --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false
Restart=always
RestartSec=10
ReadWritePaths=${APP_DIR}/data ${LOG_DIR}
PrivateTmp=yes
StandardOutput=append:${LOG_DIR}/streamlit.log
StandardError=append:${LOG_DIR}/streamlit-error.log
[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload; systemctl enable ${SERVICE_NAME}

    # Step 8: 防火墙 + 启动
    log_step "Step 8/9: 防火墙并启动"
    if command -v ufw &>/dev/null; then ufw allow ${PORT}/tcp 2>/dev/null || true; ufw allow ${STREAMLIT_PORT}/tcp 2>/dev/null || true
    elif command -v firewall-cmd &>/dev/null; then
        firewall-cmd --permanent --add-port=${PORT}/tcp 2>/dev/null || true
        firewall-cmd --permanent --add-port=${STREAMLIT_PORT}/tcp 2>/dev/null || true
        firewall-cmd --reload 2>/dev/null || true
    fi
    systemctl start ${SERVICE_NAME}; sleep 3
    systemctl is-active --quiet ${SERVICE_NAME} && log_info "✅ API 运行正常" || log_warn "检查: journalctl -u ${SERVICE_NAME} -f"

    # Step 9: 验证
    log_step "Step 9/9: 验证服务"
    curl -sf http://localhost:${PORT}/api/health >/dev/null 2>&1 && log_info "✅ 健康检查通过" || log_warn "API 还在初始化"
}

# ======================== 汇总 ========================
print_summary() {
    SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "YOUR_IP")
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   🚀 部署完成！Docker 版智能问答系统已启动                   ║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  部署方式:    ${DEPLOY_MODE}                                  ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  📡 API:         http://${SERVER_IP}:${PORT}               ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  🎨 Web 界面:    http://${SERVER_IP}:${PORT}               ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  🔍 检索模式:    ${RETRIEVAL_MODE}                              ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  🤗 HF 镜像:    ${HF_ENDPOINT}        ${GREEN}║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    if [[ "$DEPLOY_MODE" == "docker" ]]; then
        echo -e "${GREEN}║${NC}  Docker 命令:                                                   ${GREEN}║${NC}"
        echo -e "${GREEN}║${NC}    docker logs ${DOCKER_CONTAINER}           查看日志       ${GREEN}║${NC}"
        echo -e "${GREEN}║${NC}    docker restart ${DOCKER_CONTAINER}        重启服务       ${GREEN}║${NC}"
        echo -e "${GREEN}║${NC}    docker stop ${DOCKER_CONTAINER}           停止服务       ${GREEN}║${NC}"
        echo -e "${GREEN}║${NC}    docker exec -it ${DOCKER_CONTAINER} bash  进入容器       ${GREEN}║${NC}"
    else
        echo -e "${GREEN}║${NC}  systemctl start ${SERVICE_NAME}              启动         ${GREEN}║${NC}"
        echo -e "${GREEN}║${NC}  systemctl restart ${SERVICE_NAME}            重启         ${GREEN}║${NC}"
        echo -e "${GREEN}║${NC}  journalctl -u ${SERVICE_NAME} -f            查看日志     ${GREEN}║${NC}"
    fi
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

main() {
    echo "============================================================"
    echo "  招股说明书智能问答系统（Docker 版） - 一键部署"
    echo "  部署方式: ${DEPLOY_MODE}"
    echo "============================================================"
    check_root; detect_os
    if [[ "$DEPLOY_MODE" == "docker" ]]; then
        deploy_docker
    else
        deploy_traditional
    fi
    print_summary
}
main "$@"
