#!/bin/bash
# ============================================================
# 招股说明书智能问答系统（多PDF版） - 一键部署脚本
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
LOG_DIR="/var/log/${APP_NAME}"
SERVICE_NAME="${APP_NAME}"
PORT=8080
STREAMLIT_PORT=8501

# DeepSeek API 配置
DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-}"
DEEPSEEK_API_BASE="${DEEPSEEK_API_BASE:-https://api.deepseek.com}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log_info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_step()  { echo -e "\n${BLUE}━━━ $* ━━━${NC}"; }

check_root() {
    if [[ $EUID -ne 0 ]]; then
        log_error "请使用 root 权限运行: sudo ./deploy.sh"
        exit 1
    fi
}

detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$ID
        OS_VERSION=$VERSION_ID
    elif [[ -f /etc/centos-release ]]; then
        OS="centos"
    else
        log_error "不支持的操作系统"
        exit 1
    fi
    log_info "检测到系统: ${OS} ${OS_VERSION}"
}

# ======================== Step 1: 系统依赖 ========================
install_system_deps() {
    log_step "Step 1/8: 安装系统依赖"

    case $OS in
        ubuntu|debian)
            apt-get update -qq
            apt-get install -y -qq \
                python${PYTHON_VERSION} \
                python${PYTHON_VERSION}-venv \
                python${PYTHON_VERSION}-dev \
                python3-pip \
                build-essential \
                libgl1-mesa-glx \
                libglib2.0-0 \
                curl wget git \
                2>/dev/null || {
                    log_warn "apt 安装失败，尝试添加 deadsnakes PPA..."
                    apt-get install -y -qq software-properties-common
                    add-apt-repository -y ppa:deadsnakes/ppa
                    apt-get update -qq
                    apt-get install -y -qq python${PYTHON_VERSION} python${PYTHON_VERSION}-venv python${PYTHON_VERSION}-dev
                }
            ;;
        centos|rhel|rocky|almalinux)
            yum install -y epel-release || true
            yum install -y python3 python3-devel python3-pip gcc gcc-c++ make mesa-libGL glib2 curl wget git
            ;;
        *)
            log_error "不支持的发行版: ${OS}"
            exit 1
            ;;
    esac

    PYTHON_CMD="python${PYTHON_VERSION}"
    if ! command -v $PYTHON_CMD &>/dev/null; then
        PYTHON_CMD="python3"
    fi
    log_info "Python: $($PYTHON_CMD --version 2>&1)"
}

# ======================== Step 2: 创建用户和目录 ========================
setup_user_and_dirs() {
    log_step "Step 2/8: 创建应用用户和目录"

    if ! id -u $APP_USER &>/dev/null; then
        useradd --system --shell /bin/false --home-dir $APP_DIR --create-home $APP_USER
        log_info "已创建系统用户: ${APP_USER}"
    fi

    mkdir -p $APP_DIR $DATA_DIR $DATA_DIR/faiss_index $LOG_DIR
    log_info "目录: ${APP_DIR} | 数据: ${DATA_DIR} | 日志: ${LOG_DIR}"
}

# ======================== Step 3: 部署应用代码 ========================
deploy_app() {
    log_step "Step 3/8: 部署应用代码"

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    cp -r "${SCRIPT_DIR}/"* "${APP_DIR}/" 2>/dev/null || true
    cp -r "${SCRIPT_DIR}"/.* "${APP_DIR}/" 2>/dev/null || true

    # 复制所有 PDF 文件到 data 目录
    for pdf in "${SCRIPT_DIR}"/*.pdf "${SCRIPT_DIR}/data/"*.pdf; do
        [[ -f "$pdf" ]] && cp "$pdf" "${DATA_DIR}/" && log_info "PDF: $(basename "$pdf")"
    done

    chown -R ${APP_USER}:${APP_USER} ${APP_DIR} ${LOG_DIR}
    chmod -R 755 ${APP_DIR}
    log_info "应用代码部署完成"
}

# ======================== Step 4: Python 虚拟环境 ========================
setup_venv() {
    log_step "Step 4/8: 配置 Python 虚拟环境"

    $PYTHON_CMD -m venv $VENV_DIR
    source ${VENV_DIR}/bin/activate
    pip install --upgrade pip setuptools wheel -q

    if [[ -f "${APP_DIR}/requirements.txt" ]]; then
        log_info "安装项目依赖..."
        pip install -r "${APP_DIR}/requirements.txt" -q
    fi

    pip install gunicorn -q
    deactivate
    log_info "虚拟环境: ${VENV_DIR}"
}

# ======================== Step 5: 环境配置 ========================
setup_env() {
    log_step "Step 5/8: 配置环境变量"

    cat > "${APP_DIR}/.env" << EOF
# DeepSeek API
DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
DEEPSEEK_API_BASE=${DEEPSEEK_API_BASE}

# 多PDF配置
PDF_DIR=${DATA_DIR}

# 生产环境
DEBUG=False
ENVIRONMENT=production
API_PORT=${PORT}
STREAMLIT_PORT=${STREAMLIT_PORT}
EOF

    chown ${APP_USER}:${APP_USER} "${APP_DIR}/.env"
    chmod 600 "${APP_DIR}/.env"
    log_info "环境变量已写入 ${APP_DIR}/.env"
}

# ======================== Step 6: 更新配置文件路径 ========================
update_config_paths() {
    log_step "Step 6/8: 更新配置文件路径"

    # 更新 config.py 中的 PDF_DIR 指向部署目录
    sed -i "s|PDF_DIR = .*|PDF_DIR = \"${DATA_DIR}\"|g" "${APP_DIR}/config.py"
    sed -i "s|FAISS_INDEX_PATH = .*|FAISS_INDEX_PATH = \"${DATA_DIR}/faiss_index\"|g" "${APP_DIR}/config.py"

    log_info "config.py 路径已更新为部署目录"
}

# ======================== Step 7: Systemd 服务 ========================
setup_systemd() {
    log_step "Step 7/8: 配置 Systemd 服务"

    # API 服务
    cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=招股说明书智能问答系统（多PDF版） - API Server
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin"
EnvironmentFile=${APP_DIR}/.env

ExecStart=${VENV_DIR}/bin/uvicorn api_server:app \\
    --host 0.0.0.0 \\
    --port ${PORT} \\
    --workers 2 \\
    --log-level info

Restart=always
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=3

NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${APP_DIR}/data ${LOG_DIR}
PrivateTmp=yes
LimitNOFILE=65536
MemoryMax=3G

StandardOutput=append:${LOG_DIR}/api.log
StandardError=append:${LOG_DIR}/api-error.log

[Install]
WantedBy=multi-user.target
EOF

    # Streamlit 服务
    cat > /etc/systemd/system/${SERVICE_NAME}-streamlit.service << EOF
[Unit]
Description=招股说明书智能问答系统（多PDF版） - Streamlit UI
After=network.target ${SERVICE_NAME}.service

[Service]
Type=simple
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
Environment="PATH=${VENV_DIR}/bin"
EnvironmentFile=${APP_DIR}/.env

ExecStart=${VENV_DIR}/bin/streamlit run ui_app.py \\
    --server.port ${STREAMLIT_PORT} \\
    --server.address 0.0.0.0 \\
    --server.headless true \\
    --browser.gatherUsageStats false

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

    systemctl daemon-reload
    systemctl enable ${SERVICE_NAME}
    log_info "Systemd 服务配置完成"
}

# ======================== Step 8: 防火墙与启动 ========================
setup_firewall_and_start() {
    log_step "Step 8/8: 配置防火墙并启动服务"

    if command -v ufw &>/dev/null; then
        ufw allow ${PORT}/tcp comment "RAG QA API" 2>/dev/null || true
        ufw allow ${STREAMLIT_PORT}/tcp comment "RAG QA Streamlit" 2>/dev/null || true
        log_info "UFW 规则已添加"
    elif command -v firewall-cmd &>/dev/null; then
        firewall-cmd --permanent --add-port=${PORT}/tcp 2>/dev/null || true
        firewall-cmd --permanent --add-port=${STREAMLIT_PORT}/tcp 2>/dev/null || true
        firewall-cmd --reload 2>/dev/null || true
        log_info "firewalld 规则已添加"
    fi

    systemctl start ${SERVICE_NAME}
    sleep 3

    if systemctl is-active --quiet ${SERVICE_NAME}; then
        log_info "✅ API 服务运行正常"
    else
        log_warn "服务可能未正常启动: journalctl -u ${SERVICE_NAME} -f"
    fi
}

# ======================== 信息汇总 ========================
print_summary() {
    SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "YOUR_SERVER_IP")
    PDF_COUNT=$(find ${DATA_DIR} -name "*.pdf" 2>/dev/null | wc -l)

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║     🚀 部署完成！多PDF智能问答系统已启动                     ║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  📡 API 地址:     http://${SERVER_IP}:${PORT}               ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  🎨 Web 界面:     http://${SERVER_IP}:${PORT}               ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  📊 Streamlit:    http://${SERVER_IP}:${STREAMLIT_PORT}     ${GREEN}║${NC}  (需手动启用)"
    echo -e "${GREEN}║${NC}  📄 PDF 数量:     ${PDF_COUNT} 个                            ${GREEN}║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  常用命令:                                                   ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    systemctl status ${SERVICE_NAME}                         ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    journalctl -u ${SERVICE_NAME} -f                         ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    systemctl restart ${SERVICE_NAME}                        ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    systemctl start ${SERVICE_NAME}-streamlit                ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}                                                              ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  多PDF管理:                                                  ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    上传PDF:  POST /api/upload-pdf                            ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    查看列表: GET /api/pdfs                                   ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    激活文档: POST /api/set-active-pdfs                       ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    删除文档: DELETE /api/pdfs/{filename}                     ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}    重建索引: POST /api/rebuild-index                         ${GREEN}║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

main() {
    echo ""
    echo "============================================================"
    echo "  招股说明书智能问答系统（多PDF版） - 一键部署"
    echo "============================================================"
    echo ""

    check_root
    detect_os
    install_system_deps
    setup_user_and_dirs
    deploy_app
    setup_venv
    setup_env
    update_config_paths
    setup_systemd
    setup_firewall_and_start
    print_summary
}

main "$@"
