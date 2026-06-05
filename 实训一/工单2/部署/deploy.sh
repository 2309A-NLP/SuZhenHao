#!/bin/bash
# ============================================================
# 招股说明书智能问答系统 - 一键部署脚本
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

# DeepSeek API 配置（可在此处修改或部署后编辑 .env）
DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-sk-840d940fbe6647109da000608d2a011a}"
DEEPSEEK_API_BASE="${DEEPSEEK_API_BASE:-https://api.deepseek.com}"

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# ======================== 工具函数 ========================
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
    log_step "Step 1/7: 安装系统依赖"

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
                curl \
                wget \
                git \
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
            yum install -y \
                python3 \
                python3-devel \
                python3-pip \
                gcc \
                gcc-c++ \
                make \
                mesa-libGL \
                glib2 \
                curl \
                wget \
                git
            ;;
        *)
            log_error "不支持的发行版: ${OS}"
            exit 1
            ;;
    esac

    # 验证 Python
    PYTHON_CMD="python${PYTHON_VERSION}"
    if ! command -v $PYTHON_CMD &>/dev/null; then
        PYTHON_CMD="python3"
    fi
    PY_VER=$($PYTHON_CMD --version 2>&1)
    log_info "Python 版本: ${PY_VER}"
}

# ======================== Step 2: 创建用户和目录 ========================
setup_user_and_dirs() {
    log_step "Step 2/7: 创建应用用户和目录"

    # 创建系统用户（如不存在）
    if ! id -u $APP_USER &>/dev/null; then
        useradd --system --shell /bin/false --home-dir $APP_DIR --create-home $APP_USER
        log_info "已创建系统用户: ${APP_USER}"
    else
        log_info "用户 ${APP_USER} 已存在，跳过"
    fi

    # 创建目录结构
    mkdir -p $APP_DIR $DATA_DIR $DATA_DIR/faiss_index $LOG_DIR
    log_info "目录结构已创建:"
    log_info "  应用目录: ${APP_DIR}"
    log_info "  数据目录: ${DATA_DIR}"
    log_info "  日志目录: ${LOG_DIR}"
}

# ======================== Step 3: 部署应用代码 ========================
deploy_app() {
    log_step "Step 3/7: 部署应用代码"

    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

    # 复制项目文件
    log_info "从 ${SCRIPT_DIR} 复制项目文件..."
    cp -r "${SCRIPT_DIR}/"* "${APP_DIR}/" 2>/dev/null || true
    cp -r "${SCRIPT_DIR}"/.* "${APP_DIR}/" 2>/dev/null || true

    # 确保 PDF 在 data 目录下
    if [[ -f "${SCRIPT_DIR}/招股说明书1-无水印.pdf" ]]; then
        cp "${SCRIPT_DIR}/招股说明书1-无水印.pdf" "${DATA_DIR}/"
        log_info "PDF 文件已复制到 ${DATA_DIR}"
    elif [[ -f "${SCRIPT_DIR}/data/招股说明书1-无水印.pdf" ]]; then
        cp "${SCRIPT_DIR}/data/招股说明书1-无水印.pdf" "${DATA_DIR}/"
        log_info "PDF 文件已复制到 ${DATA_DIR}"
    else
        log_warn "未找到 PDF 文件，请手动将招股说明书放入 ${DATA_DIR}/"
    fi

    # 设置权限
    chown -R ${APP_USER}:${APP_USER} ${APP_DIR} ${LOG_DIR}
    chmod -R 755 ${APP_DIR}
    log_info "应用代码部署完成"
}

# ======================== Step 4: Python 虚拟环境 ========================
setup_venv() {
    log_step "Step 4/7: 配置 Python 虚拟环境"

    # 创建虚拟环境
    $PYTHON_CMD -m venv $VENV_DIR
    source ${VENV_DIR}/bin/activate

    # 升级 pip
    pip install --upgrade pip setuptools wheel -q

    # 安装依赖
    if [[ -f "${APP_DIR}/requirements.txt" ]]; then
        log_info "安装项目依赖（这可能需要几分钟）..."
        pip install -r "${APP_DIR}/requirements.txt" -q
        log_info "依赖安装完成"
    else
        log_error "requirements.txt 不存在"
        exit 1
    fi

    # 安装额外的生产依赖
    pip install gunicorn -q

    deactivate
    log_info "虚拟环境配置完成: ${VENV_DIR}"
}

# ======================== Step 5: 环境配置 ========================
setup_env() {
    log_step "Step 5/7: 配置环境变量"

    cat > "${APP_DIR}/.env" << EOF
# DeepSeek API 配置
DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY}
DEEPSEEK_API_BASE=${DEEPSEEK_API_BASE}

# PDF 文件路径
PDF_PATH=${DATA_DIR}/招股说明书1-无水印.pdf

# 生产环境配置
DEBUG=False
ENVIRONMENT=production

# 服务端口
API_PORT=${PORT}
STREAMLIT_PORT=${STREAMLIT_PORT}
EOF

    chown ${APP_USER}:${APP_USER} "${APP_DIR}/.env"
    chmod 600 "${APP_DIR}/.env"
    log_info "环境变量已写入 ${APP_DIR}/.env"
}

# ======================== Step 6: Systemd 服务 ========================
setup_systemd() {
    log_step "Step 6/7: 配置 Systemd 服务"

    # --- API 服务 (FastAPI) ---
    cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=招股说明书智能问答系统 - API Server
After=network.target
Wants=network-online.target

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
    --log-level info \\
    --access-log \\
    --log-config logging.conf

Restart=always
RestartSec=5
StartLimitIntervalSec=60
StartLimitBurst=3

# 安全加固
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=${APP_DIR}/data ${LOG_DIR}
PrivateTmp=yes

# 资源限制
LimitNOFILE=65536
MemoryMax=2G

StandardOutput=append:${LOG_DIR}/api.log
StandardError=append:${LOG_DIR}/api-error.log

[Install]
WantedBy=multi-user.target
EOF

    # --- Streamlit 服务（可选） ---
    cat > /etc/systemd/system/${SERVICE_NAME}-streamlit.service << EOF
[Unit]
Description=招股说明书智能问答系统 - Streamlit UI
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

    # 重新加载 systemd
    systemctl daemon-reload
    systemctl enable ${SERVICE_NAME}
    log_info "Systemd 服务已配置并启用"
}

# ======================== Step 7: 防火墙与启动 ========================
setup_firewall_and_start() {
    log_step "Step 7/7: 配置防火墙并启动服务"

    # 配置防火墙
    if command -v ufw &>/dev/null; then
        ufw allow ${PORT}/tcp comment "RAG QA API" 2>/dev/null || true
        ufw allow ${STREAMLIT_PORT}/tcp comment "RAG QA Streamlit" 2>/dev/null || true
        log_info "UFW 防火墙规则已添加"
    elif command -v firewall-cmd &>/dev/null; then
        firewall-cmd --permanent --add-port=${PORT}/tcp 2>/dev/null || true
        firewall-cmd --permanent --add-port=${STREAMLIT_PORT}/tcp 2>/dev/null || true
        firewall-cmd --reload 2>/dev/null || true
        log_info "firewalld 防火墙规则已添加"
    else
        log_warn "未检测到防火墙工具，请手动开放端口 ${PORT} 和 ${STREAMLIT_PORT}"
    fi

    # 首次构建索引（后台执行）
    log_info "首次启动将自动构建向量索引..."

    # 启动 API 服务
    systemctl start ${SERVICE_NAME}
    log_info "API 服务已启动 (端口 ${PORT})"

    # 启动 Streamlit（可选，默认不启用）
    # systemctl start ${SERVICE_NAME}-streamlit
    # log_info "Streamlit 服务已启动 (端口 ${STREAMLIT_PORT})"

    # 等待服务启动
    sleep 3
    if systemctl is-active --quiet ${SERVICE_NAME}; then
        log_info "✅ API 服务运行正常"
    else
        log_warn "API 服务可能未正常启动，请检查日志: journalctl -u ${SERVICE_NAME} -f"
    fi
}

# ======================== Nginx 反向代理（可选） ========================
setup_nginx() {
    log_step "[可选] 配置 Nginx 反向代理"

    if ! command -v nginx &>/dev/null; then
        log_info "Nginx 未安装，跳过反向代理配置"
        log_info "如需安装: apt install nginx && 重新运行此脚本"
        return
    fi

    read -p "是否配置 Nginx 反向代理？(y/N): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "跳过 Nginx 配置"
        return
    fi

    read -p "请输入域名（如 qa.example.com，留空则使用默认）: " DOMAIN
    DOMAIN=${DOMAIN:-"_"}

    cat > /etc/nginx/sites-available/${APP_NAME} << EOF
server {
    listen 80;
    server_name ${DOMAIN};

    client_max_body_size 50M;

    # API 服务
    location /api/ {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }

    # 前端静态文件
    location / {
        proxy_pass http://127.0.0.1:${PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
    }

    # 静态资源缓存
    location /static/ {
        proxy_pass http://127.0.0.1:${PORT}/static/;
        expires 7d;
        add_header Cache-Control "public, immutable";
    }
}
EOF

    ln -sf /etc/nginx/sites-available/${APP_NAME} /etc/nginx/sites-enabled/
    nginx -t && systemctl reload nginx
    log_info "Nginx 反向代理配置完成"
}

# ======================== 信息汇总 ========================
print_summary() {
    SERVER_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "YOUR_SERVER_IP")

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║          🚀 部署完成！招股说明书智能问答系统已启动           ║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}                                                              ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  📡 API 服务地址:  http://${SERVER_IP}:${PORT}              ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  🎨 Web 聊天界面:  http://${SERVER_IP}:${PORT}              ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  📊 Streamlit UI:  http://${SERVER_IP}:${STREAMLIT_PORT}    ${GREEN}║${NC}  (需手动启用)"
    echo -e "${GREEN}║${NC}                                                              ${GREEN}║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  常用命令:                                                   ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}                                                              ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  查看状态:  systemctl status ${SERVICE_NAME}               ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  查看日志:  journalctl -u ${SERVICE_NAME} -f               ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  重启服务:  systemctl restart ${SERVICE_NAME}              ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  停止服务:  systemctl stop ${SERVICE_NAME}                 ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  启动Stream: systemctl start ${SERVICE_NAME}-streamlit     ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}                                                              ${GREEN}║${NC}"
    echo -e "${GREEN}╠══════════════════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║${NC}  配置文件:                                                   ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  环境变量:  ${APP_DIR}/.env                                  ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  应用配置:  ${APP_DIR}/config.py                             ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  日志目录:  ${LOG_DIR}/                                       ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}  数据目录:  ${DATA_DIR}/                                      ${GREEN}║${NC}"
    echo -e "${GREEN}║${NC}                                                              ${GREEN}║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"
    echo ""
}

# ======================== 主流程 ========================
main() {
    echo ""
    echo "============================================================"
    echo "  招股说明书智能问答系统 - 一键部署"
    echo "  目标目录: ${APP_DIR}"
    echo "============================================================"
    echo ""

    check_root
    detect_os
    install_system_deps
    setup_user_and_dirs
    deploy_app
    setup_venv
    setup_env
    setup_systemd
    setup_firewall_and_start
    setup_nginx
    print_summary
}

main "$@"
