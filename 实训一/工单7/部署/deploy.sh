#!/bin/bash
# ============================================================
# 招股说明书智能问答系统（完整版 + 混合检索） - 一键部署脚本
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

# API 配置
DEEPSEEK_API_KEY="***"
DEEPSEEK_API_BASE="${DEEPSEEK_API_BASE:-https://api.deepseek.com}"
QWEN_VL_API_KEY="***"
QWEN_VL_API_BASE="${QWEN_VL_API_BASE:-https://dashscope.aliyuncs.com/compatible-mode/v1}"

# 检索模式：vector / bm25 / hybrid（默认 hybrid）
RETRIEVAL_MODE="${RETRIEVAL_MODE:-hybrid}"

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

# ======================== Step 1: 系统依赖 ========================
install_system_deps() {
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
}

# ======================== Step 2: 用户和目录 ========================
setup_user_and_dirs() {
    log_step "Step 2/9: 创建用户和目录"
    id -u $APP_USER &>/dev/null || useradd --system --shell /bin/false --home-dir $APP_DIR --create-home $APP_USER
    mkdir -p $APP_DIR $DATA_DIR $DATA_DIR/faiss_index $IMAGE_DIR $LOG_DIR
    log_info "目录: ${APP_DIR}"
}

# ======================== Step 3: 部署代码 ========================
deploy_app() {
    log_step "Step 3/9: 部署应用代码"
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cp -r "${SCRIPT_DIR}/"* "${APP_DIR}/" 2>/dev/null || true
    cp -r "${SCRIPT_DIR}"/.* "${APP_DIR}/" 2>/dev/null || true
    for pdf in "${SCRIPT_DIR}"/*.pdf "${SCRIPT_DIR}/data/"*.pdf; do
        [[ -f "$pdf" ]] && cp "$pdf" "${DATA_DIR}/" && log_info "PDF: $(basename "$pdf")"
    done
    chown -R ${APP_USER}:${APP_USER} ${APP_DIR} ${LOG_DIR}; chmod -R 755 ${APP_DIR}
    log_info "代码部署完成"
}

# ======================== Step 4: 虚拟环境 ========================
setup_venv() {
    log_step "Step 4/9: 配置虚拟环境"
    $PYTHON_CMD -m venv $VENV_DIR; source ${VENV_DIR}/bin/activate
    pip install --upgrade pip setuptools wheel -q
    [[ -f "${APP_DIR}/requirements.txt" ]] && {
        log_info "安装依赖（含 rank-bm25 + jieba + sentence-transformers）..."
        pip install -r "${APP_DIR}/requirements.txt" -q
    }
    pip install gunicorn -q; deactivate
    log_info "虚拟环境: ${VENV_DIR}"
}

# ======================== Step 5: 环境变量 ========================
setup_env() {
    log_step "Step 5/9: 配置环境变量"
    cat > "${APP_DIR}/.env" << EOF
# DeepSeek API
DEEPSEEK_API_KEY=***
DEEPSEEK_API_BASE=${DEEPSEEK_API_BASE}

# 阿里云百炼 Qwen-VL（图片理解）
QWEN_VL_API_KEY=***
QWEN_VL_API_BASE=${QWEN_VL_API_BASE}
QWEN_VL_MODEL=qwen-vl-plus-latest

# 多PDF配置
PDF_DIR=${DATA_DIR}

# 检索模式: vector / bm25 / hybrid
RETRIEVAL_MODE=${RETRIEVAL_MODE}

# 图片配置
IMAGE_DIR=${IMAGE_DIR}
MAX_IMAGE_SIZE_MB=10

# 生产环境
DEBUG=False
ENVIRONMENT=production
API_PORT=${PORT}
STREAMLIT_PORT=${STREAMLIT_PORT}
EOF
    chown ${APP_USER}:${APP_USER} "${APP_DIR}/.env"; chmod 600 "${APP_DIR}/.env"
    log_info ".env 已写入（检索模式: ${RETRIEVAL_MODE}）"
}

# ======================== Step 6: 更新配置路径 ========================
update_config_paths() {
    log_step "Step 6/9: 更新配置路径"
    sed -i "s|PDF_DIR = .*|PDF_DIR = \"${DATA_DIR}\"|g" "${APP_DIR}/config.py"
    sed -i "s|FAISS_INDEX_PATH = .*|FAISS_INDEX_PATH = \"${DATA_DIR}/faiss_index\"|g" "${APP_DIR}/config.py"
    sed -i "s|IMAGE_DIR = .*|IMAGE_DIR = \"${IMAGE_DIR}\"|g" "${APP_DIR}/config.py"
    sed -i 's|r"C:\\Users\\.*\\m3e-base"|"shibing624/text2vec-base-chinese"|g' "${APP_DIR}/config.py"
    sed -i 's|r"C:\\Users\\.*\\bge-reranker-base"|"BAAI/bge-reranker-base"|g' "${APP_DIR}/config.py"
    log_info "config.py 路径已更新"
}

# ======================== Step 7: Systemd ========================
setup_systemd() {
    log_step "Step 7/9: 配置 Systemd 服务"
    cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=RAG 问答系统（混合检索版） - API
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin"
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
EnvironmentFile=${APP_DIR}/.env
ExecStart=${VENV_DIR}/bin/streamlit run ui_app.py --server.port ${STREAMLIT_PORT} --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false
Restart=always
RestartSec=10
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${APP_DIR}/data ${LOG_DIR}
PrivateTmp=yes
StandardOutput=append:${LOG_DIR}/streamlit.log
StandardError=append:${LOG_DIR}/streamlit-error.log
[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload; systemctl enable ${SERVICE_NAME}
    log_info "Systemd 服务配置完成"
}

# ======================== Step 8: 防火墙 + 启动 ========================
setup_firewall_and_start() {
    log_step "Step 8/9: 防火墙并启动"
    if command -v ufw &>/dev/null; then ufw allow ${PORT}/tcp 2>/dev/null || true; ufw allow ${STREAMLIT_PORT}/tcp 2>/dev/null || true
    elif command -v firewall-cmd &>/dev/null; then
        firewall-cmd --permanent --add-port=${PORT}/tcp 2>/dev/null || true
        firewall-cmd --permanent --add-port=${STREAMLIT_PORT}/tcp 2>/dev/null || true
        firewall-cmd --reload 2>/dev/null || true
    fi
    systemctl start ${SERVICE_NAME}; sleep 3
    systemctl is-active --quiet ${SERVICE_NAME} && log_info "✅ API 运行正常" || log_warn "检查: journalctl -u ${SERVICE_NAME} -f"
}

# ======================== Step 9: 验证 ========================
verify_services() {
    log_step "Step 9/9: 验证服务"
    curl -sf http://localhost:${PORT}/api/health >/dev/null 2>&1 && log_info "✅ 健康检查通过" || log_warn "API 还在初始化"
    curl -sf http://localhost:${PORT}/api/image-status >/dev/null 2>&1 && log_info "✅ 图片服务就绪" || log_warn "图片服务未配置"
}

# ======================== 汇总 ========================
print_summary() {
    SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "YOUR_IP")
    PDF_COUNT=$(find ${DATA_DIR} -name "*.pdf" 2>/dev/null | wc -l)
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   🚀 部署完成！混合检索智能问答系统已启动                     ║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  📡 API:         http://${SERVER_IP}:${PORT}               ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  🎨 Web 界面:    http://${SERVER_IP}:${PORT}               ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  📊 Streamlit:   http://${SERVER_IP}:${STREAMLIT_PORT}     ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  🔍 检索模式:    ${RETRIEVAL_MODE}                              ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  📄 PDF:         ${PDF_COUNT} 个                               ${GREEN}║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  核心接口:                                                      ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    POST /api/chat              普通问答                         ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    POST /api/chat/stream       流式问答（SSE）                 ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    GET  /api/retrieval-mode    查看检索模式                     ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    POST /api/retrieval-mode    切换检索模式                     ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    POST /api/analyze-image     图片分析                         ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    POST /api/image-chat        图片+文档问答                    ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    GET  /api/pdfs              PDF 列表                         ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    POST /api/stt               语音转文字                       ${GREEN}║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

main() {
    echo "============================================================"
    echo "  招股说明书智能问答系统（混合检索版） - 一键部署"
    echo "  检索模式: vector / bm25 / hybrid"
    echo "============================================================"
    check_root; detect_os
    install_system_deps; setup_user_and_dirs; deploy_app
    setup_venv; setup_env; update_config_paths
    setup_systemd; setup_firewall_and_start; verify_services
    print_summary
}
main "$@"
