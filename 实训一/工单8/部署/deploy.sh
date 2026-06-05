#!/bin/bash
# ============================================================
# 智能文档问答系统（RAG + 知识图谱 + 语音识别） - 一键部署脚本
# 适用环境: Ubuntu 20.04+ / CentOS 7+ / Debian 11+
# 使用方式: chmod +x deploy.sh && sudo ./deploy.sh
# ============================================================

set -euo pipefail

# ======================== 配置区 ========================
APP_NAME="rag-kg-qa"
APP_USER="ragapp"
APP_DIR="/opt/${APP_NAME}"
PYTHON_VERSION="3.10"
VENV_DIR="${APP_DIR}/venv"
UPLOAD_DIR="${APP_DIR}/uploads"
VECTOR_STORE_DIR="${APP_DIR}/vector_store"
KG_OUTPUT_DIR="${APP_DIR}/kg_output"
LOG_DIR="/var/log/${APP_NAME}"
SERVICE_NAME="${APP_NAME}"
STREAMLIT_PORT=8501

# API 配置
MIMO_API_KEY="${MIMO_API_KEY:-tp-crncudh1306abwos94du3c0u7898mkyvxxn9pmq3klsqsnb3}"
MIMO_BASE_URL="${MIMO_BASE_URL:-https://token-plan-cn.xiaomimimo.com/v1}"
MIMO_MODEL="${MIMO_MODEL:-mimo-v2.5-pro}"

# Embedding 模型（在线下载）
EMBEDDING_MODEL="${EMBEDDING_MODEL:-BAAI/bge-base-zh-v1.5}"

# Whisper 模型大小: tiny/base/small/medium/large
WHISPER_MODEL_SIZE="${WHISPER_MODEL_SIZE:-base}"

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
    log_step "Step 1/8: 安装系统依赖"
    case $OS in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq python${PYTHON_VERSION} python${PYTHON_VERSION}-venv \
                python${PYTHON_VERSION}-dev python3-pip build-essential \
                libgl1-mesa-glx libglib2.0-0 libjpeg-dev libpng-dev \
                ffmpeg portaudio19-dev curl wget git 2>/dev/null || {
                    apt-get install -y -qq software-properties-common
                    add-apt-repository -y ppa:deadsnakes/ppa; apt-get update -qq
                    apt-get install -y -qq python${PYTHON_VERSION} python${PYTHON_VERSION}-venv
                }
            ;;
        centos|rhel|rocky|almalinux)
            yum install -y epel-release || true
            yum install -y python3 python3-devel python3-pip gcc gcc-c++ make \
                mesa-libGL glib2 libjpeg-turbo-devel libpng-devel \
                ffmpeg portaudio-devel curl wget git
            ;;
        *) log_error "不支持: ${OS}"; exit 1 ;;
    esac
    PYTHON_CMD="python${PYTHON_VERSION}"; command -v $PYTHON_CMD &>/dev/null || PYTHON_CMD="python3"
    log_info "Python: $($PYTHON_CMD --version 2>&1)"
}

# ======================== Step 2: 用户和目录 ========================
setup_user_and_dirs() {
    log_step "Step 2/8: 创建用户和目录"
    id -u $APP_USER &>/dev/null || useradd --system --shell /bin/false --home-dir $APP_DIR --create-home $APP_USER
    mkdir -p $APP_DIR $UPLOAD_DIR $VECTOR_STORE_DIR $KG_OUTPUT_DIR $LOG_DIR
    log_info "目录: ${APP_DIR}"
}

# ======================== Step 3: 部署代码 ========================
deploy_app() {
    log_step "Step 3/8: 部署应用代码"
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cp -r "${SCRIPT_DIR}/"* "${APP_DIR}/" 2>/dev/null || true
    cp -r "${SCRIPT_DIR}"/.* "${APP_DIR}/" 2>/dev/null || true
    chown -R ${APP_USER}:${APP_USER} ${APP_DIR} ${LOG_DIR}; chmod -R 755 ${APP_DIR}
    log_info "代码部署完成"
}

# ======================== Step 4: 虚拟环境 ========================
setup_venv() {
    log_step "Step 4/8: 配置虚拟环境"
    $PYTHON_CMD -m venv $VENV_DIR; source ${VENV_DIR}/bin/activate
    pip install --upgrade pip setuptools wheel -q
    [[ -f "${APP_DIR}/requirements.txt" ]] && {
        log_info "安装依赖（含 langchain + networkx + pyvis + whisper）..."
        pip install -r "${APP_DIR}/requirements.txt" -q
    }
    pip install gunicorn -q; deactivate
    log_info "虚拟环境: ${VENV_DIR}"
}

# ======================== Step 5: 更新配置 ========================
update_config() {
    log_step "Step 5/8: 更新配置文件"
    cat > "${APP_DIR}/.env" << EOF
# MiMo API
MIMO_API_KEY=${MIMO_API_KEY}
MIMO_BASE_URL=${MIMO_BASE_URL}
MIMO_MODEL=${MIMO_MODEL}

# Embedding 模型（在线下载）
EMBEDDING_MODEL=${EMBEDDING_MODEL}

# Whisper
WHISPER_MODEL_SIZE=${WHISPER_MODEL_SIZE}

# 路径
UPLOAD_DIR=${UPLOAD_DIR}
VECTOR_STORE_DIR=${VECTOR_STORE_DIR}
KG_OUTPUT_DIR=${KG_OUTPUT_DIR}
EOF

    # 更新 config.py 中的路径和模型
    sed -i "s|MIMO_API_KEY = .*|MIMO_API_KEY = \"${MIMO_API_KEY}\"|g" "${APP_DIR}/config.py"
    sed -i "s|MIMO_BASE_URL = .*|MIMO_BASE_URL = \"${MIMO_BASE_URL}\"|g" "${APP_DIR}/config.py"
    sed -i "s|UPLOAD_DIR = .*|UPLOAD_DIR = \"${UPLOAD_DIR}\"|g" "${APP_DIR}/config.py"
    sed -i "s|VECTOR_STORE_DIR = .*|VECTOR_STORE_DIR = \"${VECTOR_STORE_DIR}\"|g" "${APP_DIR}/config.py"
    sed -i "s|KG_OUTPUT_DIR = .*|KG_OUTPUT_DIR = \"${KG_OUTPUT_DIR}\"|g" "${APP_DIR}/config.py"
    sed -i 's|EMBEDDING_MODEL_PATH = r"C:\\Users\\.*|EMBEDDING_MODEL_PATH = "'"${EMBEDDING_MODEL}"'"|g' "${APP_DIR}/config.py"
    sed -i 's|EMBEDDING_MODEL_NAME = .*|EMBEDDING_MODEL_NAME = "'"${EMBEDDING_MODEL}"'"|g' "${APP_DIR}/config.py"
    chown ${APP_USER}:${APP_USER} "${APP_DIR}/.env"; chmod 600 "${APP_DIR}/.env"
    log_info "配置已更新"
}

# ======================== Step 6: Streamlit 配置 ========================
setup_streamlit() {
    log_step "Step 6/8: 配置 Streamlit"
    mkdir -p "${APP_DIR}/.streamlit"
    cat > "${APP_DIR}/.streamlit/config.toml" << EOF
[server]
port = ${STREAMLIT_PORT}
address = "0.0.0.0"
headless = true
maxUploadSize = 200
enableCORS = false
enableXsrfProtection = false

[browser]
gatherUsageStats = false

[theme]
primaryColor = "#7c3aed"
backgroundColor = "#0d0d0d"
secondaryBackgroundColor = "#1a1a1a"
textColor = "#ececec"
font = "sans serif"
EOF
    chown -R ${APP_USER}:${APP_USER} "${APP_DIR}/.streamlit"
    log_info "Streamlit 配置完成"
}

# ======================== Step 7: Systemd ========================
setup_systemd() {
    log_step "Step 7/8: 配置 Systemd 服务"
    cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=智能文档问答系统（RAG + 知识图谱 + 语音识别）
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin"
EnvironmentFile=${APP_DIR}/.env
ExecStart=${VENV_DIR}/bin/streamlit run app.py --server.port ${STREAMLIT_PORT} --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false
Restart=always
RestartSec=10
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${APP_DIR}/uploads ${APP_DIR}/vector_store ${APP_DIR}/kg_output ${LOG_DIR}
PrivateTmp=yes
MemoryMax=6G
StandardOutput=append:${LOG_DIR}/app.log
StandardError=append:${LOG_DIR}/app-error.log
[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload; systemctl enable ${SERVICE_NAME}
    log_info "Systemd 服务配置完成"
}

# ======================== Step 8: 防火墙 + 启动 + 验证 ========================
setup_firewall_and_start() {
    log_step "Step 8/8: 防火墙、启动、验证"
    if command -v ufw &>/dev/null; then ufw allow ${STREAMLIT_PORT}/tcp 2>/dev/null || true
    elif command -v firewall-cmd &>/dev/null; then
        firewall-cmd --permanent --add-port=${STREAMLIT_PORT}/tcp 2>/dev/null || true
        firewall-cmd --reload 2>/dev/null || true
    fi
    systemctl start ${SERVICE_NAME}; sleep 3
    systemctl is-active --quiet ${SERVICE_NAME} && log_info "✅ 服务运行正常" || log_warn "检查: journalctl -u ${SERVICE_NAME} -f"
}

# ======================== 汇总 ========================
print_summary() {
    SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "YOUR_IP")
    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║   🚀 部署完成！智能文档问答系统已启动                         ║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  🎨 Streamlit:   http://${SERVER_IP}:${STREAMLIT_PORT}     ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  🤖 LLM:         MiMo ${MIMO_MODEL}                  ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  🔍 Embedding:   ${EMBEDDING_MODEL}         ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  🎤 Whisper:     ${WHISPER_MODEL_SIZE}                          ${GREEN}║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  功能:                                                          ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    📄 PDF 文档解析 + 向量化                                     ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    💬 RAG 智能问答（多轮对话）                                 ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    🕸️ 知识图谱（实体关系抽取 + 交互式可视化）                 ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    🎤 语音识别（Whisper 本地模型）                            ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    🌐 中英文双语支持                                           ${GREEN}║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

main() {
    echo "============================================================"
    echo "  智能文档问答系统（RAG + 知识图谱 + 语音识别） - 一键部署"
    echo "  LLM: MiMo | Embedding: bge-base-zh | KG: NetworkX + Pyvis"
    echo "============================================================"
    check_root; detect_os
    install_system_deps; setup_user_and_dirs; deploy_app
    setup_venv; update_config; setup_streamlit
    setup_systemd; setup_firewall_and_start
    print_summary
}
main "$@"
