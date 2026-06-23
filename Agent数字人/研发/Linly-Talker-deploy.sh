#!/bin/bash
# ============================================================
# Linly-Talker 数字人智能对话系统 — 完整部署脚本
# 项目路径: D:\DigitalHuman\Linly-Talker
# 用途: 一键部署数字人对话系统（含环境检查、模型验证、依赖安装、服务启动）
# 适用环境: Windows/Linux/Mac/WSL, Python 3.10, CUDA 11.8+
# ============================================================

set -e

# ---- 颜色定义 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
NC='\033[0m'

# ---- 项目路径 ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ============================================================
# 工具函数
# ============================================================
print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════════╗"
    echo "║                                                              ║"
    echo "║     🎭 Linly-Talker 数字人智能对话系统                       ║"
    echo "║     Digital Human Intelligent Dialogue System                ║"
    echo "║     — 部署脚本 v1.0 —                                       ║"
    echo "║                                                              ║"
    echo "╚══════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "\n${BLUE}[$1/8]${NC} ${BOLD}$2${NC}"
}

print_ok()   { echo -e "  ${GREEN}✔${NC} $1"; }
print_warn() { echo -e "  ${YELLOW}⚠${NC} $1"; }
print_fail() { echo -e "  ${RED}✘${NC} $1"; }
print_info() { echo -e "  ${CYAN}ℹ${NC} $1"; }
print_skip() { echo -e "  ${MAGENTA}○${NC} $1 (可选，已跳过)"; }

# ============================================================
# Step 1: 系统环境检查
# ============================================================
step1_check_system() {
    print_step 1 "系统环境检查"

    # 操作系统
    OS="$(uname -s 2>/dev/null || echo Windows)"
    print_info "操作系统: $OS"

    # Python
    PYTHON=""
    for cmd in python3.10 python3 python; do
        if command -v "$cmd" &>/dev/null; then
            PYTHON=$(command -v "$cmd")
            break
        fi
    done
    if [ -z "$PYTHON" ]; then
        print_fail "未找到 Python，请安装 Python 3.10"
        exit 1
    fi

    PY_VERSION=$($PYTHON --version 2>&1 | grep -oP '\d+\.\d+')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

    if [ "$PY_MAJOR" -ne 3 ] || [ "$PY_MINOR" -ne 10 ]; then
        print_warn "推荐 Python 3.10，当前: $PY_VERSION (可能存在兼容性问题)"
    else
        print_ok "Python 版本: $PY_VERSION ✓"
    fi

    # pip
    PIP="$PYTHON -m pip"
    if $PYTHON -m pip --version &>/dev/null; then
        print_ok "pip 可用"
    else
        print_fail "pip 不可用，请安装 pip"
        exit 1
    fi

    # CUDA
    if command -v nvidia-smi &>/dev/null; then
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)
        GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1)
        CUDA_VER=$(nvidia-smi 2>/dev/null | grep "CUDA Version" | awk '{print $9}')
        print_ok "GPU: $GPU_NAME ($GPU_MEM)"
        print_ok "CUDA: $CUDA_VER"

        # 检查显存是否足够
        GPU_MEM_MB=$(echo "$GPU_MEM" | grep -oP '\d+' | head -1)
        if [ "$GPU_MEM_MB" -lt 4000 ]; then
            print_warn "显存不足 4GB，部分功能可能无法运行"
        fi
    else
        print_warn "未检测到 NVIDIA GPU，将使用 CPU 模式（速度较慢）"
    fi

    # FFmpeg
    if command -v ffmpeg &>/dev/null; then
        print_ok "FFmpeg 可用: $(ffmpeg -version 2>&1 | head -1)"
    else
        print_warn "FFmpeg 未安装，视频处理可能受限"
        print_info "安装: sudo apt install ffmpeg / choco install ffmpeg"
    fi

    # Git
    if command -v git &>/dev/null; then
        print_ok "Git 可用: $(git --version)"
    else
        print_warn "Git 未安装，模型下载可能受限"
    fi
}

# ============================================================
# Step 2: 项目目录验证
# ============================================================
step2_verify_project() {
    print_step 2 "项目目录验证"

    # 核心文件检查
    local core_files=(
        "webui.py"
        "app.py"
        "configs.py"
        "requirements_webui.txt"
    )
    for f in "${core_files[@]}"; do
        if [ -f "$SCRIPT_DIR/$f" ]; then
            print_ok "核心文件: $f"
        else
            print_fail "核心文件缺失: $f"
            exit 1
        fi
    done

    # 核心模块目录检查
    local core_dirs=(
        "src"
        "ASR"
        "TTS"
        "LLM"
        "TFG"
        "checkpoints"
        "inputs"
        "examples"
    )
    for d in "${core_dirs[@]}"; do
        if [ -d "$SCRIPT_DIR/$d" ]; then
            local count=$(find "$SCRIPT_DIR/$d" -type f | wc -l)
            print_ok "模块目录: $d/ ($count 个文件)"
        else
            print_warn "目录不存在: $d/"
        fi
    done

    # 子模块目录
    local sub_dirs=(
        "Qwen"
        "CosyVoice"
        "GPT_SoVITS"
        "FunASR"
        "Whisper"
        "Musetalk"
        "gfpgan"
        "ChatTTS"
    )
    for d in "${sub_dirs[@]}"; do
        if [ -d "$SCRIPT_DIR/$d" ]; then
            local count=$(find "$SCRIPT_DIR/$d" -type f 2>/dev/null | wc -l)
            local size=$(du -sh "$SCRIPT_DIR/$d" 2>/dev/null | cut -f1)
            print_ok "子模块: $d/ ($count 文件, $size)"
        else
            print_warn "子模块不存在: $d/ (需手动下载)"
        fi
    done
}

# ============================================================
# Step 3: 模型权重验证
# ============================================================
step3_verify_models() {
    print_step 3 "模型权重验证"

    CK_DIR="$SCRIPT_DIR/checkpoints"

    # SadTalker 模型
    if [ -f "$CK_DIR/SadTalker_V0.0.2_256.safetensors" ]; then
        local size=$(du -h "$CK_DIR/SadTalker_V0.0.2_256.safetensors" | cut -f1)
        print_ok "SadTalker 模型: $size"
    else
        print_fail "SadTalker 模型缺失"
    fi

    # Wav2Lip 模型
    for model in "wav2lip.pth" "wav2lip_gan.pth" "wav2lipv2.pth"; do
        if [ -f "$CK_DIR/$model" ]; then
            local size=$(du -h "$CK_DIR/$model" | cut -f1)
            print_ok "Wav2Lip 模型: $model ($size)"
        else
            print_warn "Wav2Lip 模型缺失: $model"
        fi
    done

    # CosyVoice 模型
    if [ -d "$CK_DIR/CosyVoice_ckpt" ]; then
        local cv_size=$(du -sh "$CK_DIR/CosyVoice_ckpt" | cut -f1)
        print_ok "CosyVoice 模型: $cv_size"
    else
        print_warn "CosyVoice 模型缺失"
    fi

    # GFPGAN 模型
    if [ -f "$SCRIPT_DIR/gfpgan/weights/GFPGANv1.4.pth" ]; then
        print_ok "GFPGAN 人脸增强模型"
    else
        print_warn "GFPGAN 模型缺失 (可选)"
    fi

    # Whisper 模型
    for model in "tiny.pt" "base.pt"; do
        if [ -f "$SCRIPT_DIR/Whisper/$model" ]; then
            print_ok "Whisper 模型: $model"
        else
            print_warn "Whisper 模型缺失: $model"
        fi
    done

    # Musetalk 模型
    if [ -f "$SCRIPT_DIR/Musetalk/models/musetalk/pytorch_model.bin" ]; then
        print_ok "MuseTalk 模型"
    else
        print_warn "MuseTalk 模型缺失"
    fi

    # Qwen 模型
    if [ -d "$SCRIPT_DIR/Qwen/Qwen-1_8B-Chat" ]; then
        local qw_size=$(du -sh "$SCRIPT_DIR/Qwen/Qwen-1_8B-Chat" | cut -f1)
        print_ok "Qwen-1.8B-Chat 模型: $qw_size"
    else
        print_warn "Qwen 模型缺失 (可选，LLM 模块)"
    fi

    # GPT-SoVITS 模型
    if [ -d "$SCRIPT_DIR/GPT_SoVITS/pretrained_models" ]; then
        print_ok "GPT-SoVITS 预训练模型"
    else
        print_warn "GPT-SoVITS 模型缺失 (可选，声音克隆)"
    fi

    # FunASR 模型
    local funasr_models=(
        "speech_fsmn_vad_zh-cn-16k-common-pytorch"
        "speech_seaco_paraformer_large_asr_nat-zh-cn-16k-common-vocab8404-pytorch"
        "punc_ct-transformer_zh-cn-common-vocab272727-pytorch"
    )
    for m in "${funasr_models[@]}"; do
        if [ -d "$SCRIPT_DIR/FunASR/$m" ]; then
            print_ok "FunASR 模型: $m"
        else
            print_warn "FunASR 模型缺失: $m"
        fi
    done
}

# ============================================================
# Step 4: 安装 Python 依赖
# ============================================================
step4_install_deps() {
    print_step 4 "安装 Python 依赖"

    cd "$SCRIPT_DIR"

    echo -e "  ${CYAN}安装核心依赖 (requirements_webui.txt)...${NC}"
    $PIP install --upgrade pip -q 2>/dev/null

    # PyTorch (CUDA 11.8)
    echo -e "  ${CYAN}检查 PyTorch...${NC}"
    if $PYTHON -c "import torch; print(torch.__version__)" 2>/dev/null | grep -q "cu1"; then
        print_ok "PyTorch (CUDA) 已安装: $($PYTHON -c 'import torch; print(torch.__version__)')"
    else
        print_info "安装 PyTorch (CUDA 11.8)..."
        $PIP install torch torchvision torchaudio \
            --index-url https://download.pytorch.org/whl/cu118 -q 2>&1 | tail -3
    fi

    # 核心依赖
    echo -e "  ${CYAN}安装核心依赖...${NC}"
    $PIP install -r requirements_webui.txt -q 2>&1 | tail -10
    print_ok "核心依赖安装完成"

    # 验证关键模块
    local modules=("torch" "gradio" "numpy" "scipy" "cv2" "transformers" "librosa")
    local names=("PyTorch" "Gradio" "NumPy" "SciPy" "OpenCV" "Transformers" "Librosa")

    echo -e "\n  ${CYAN}验证关键模块...${NC}"
    for i in "${!modules[@]}"; do
        if $PYTHON -c "import ${modules[$i]}" 2>/dev/null; then
            print_ok "${names[$i]} ✓"
        else
            print_warn "${names[$i]} 导入失败"
        fi
    done
}

# ============================================================
# Step 5: 可选组件安装
# ============================================================
step5_optional_components() {
    print_step 5 "可选组件检查"

    echo -e "  ${CYAN}以下为可选组件，根据需要选择安装:${NC}\n"

    # PaddleTTS
    if [ -d "$SCRIPT_DIR/PaddleSpeech" ] || [ -f "$SCRIPT_DIR/TTS/PaddleTTS.py" ]; then
        print_info "PaddleTTS: 已存在"
    else
        print_skip "PaddleTTS (百度语音合成) — 需离线环境"
        print_info "  安装: pip install paddlepaddle==2.5.2 paddlespeech==1.4.1"
    fi

    # ER-NeRF
    print_skip "ER-NeRF (NeRF 数字人) — 需额外编译"
    print_info "  参考: TFG/README.md"

    # MuseTalk
    if [ -d "$SCRIPT_DIR/Musetalk" ]; then
        print_info "MuseTalk: 已存在 (实时对话)"
        # 检查 mmcv 等依赖
        if $PYTHON -c "import mmcv" 2>/dev/null; then
            print_ok "mmcv 已安装"
        else
            print_warn "mmcv 未安装 (MuseTalk 需要)"
            print_info "  安装: pip install --no-cache-dir -U openmim && mim install mmengine && mim install 'mmcv>=2.0.1' && mim install 'mmdet>=3.1.0' && mim install 'mmpose>=1.1.0'"
        fi
    else
        print_skip "MuseTalk (实时唇形同步)"
    fi

    # SSL 证书 (麦克风对话需要)
    if [ -f "$SCRIPT_DIR/https_cert/cert.pem" ] && [ -f "$SCRIPT_DIR/https_cert/key.pem" ]; then
        print_ok "SSL 证书已配置 (支持麦克风对话)"
    else
        print_warn "SSL 证书缺失 (麦克风对话需要 HTTPS)"
        print_info "  生成: openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes"
    fi
}

# ============================================================
# Step 6: 配置检查
# ============================================================
step6_check_config() {
    print_step 6 "配置文件检查"

    if [ -f "$SCRIPT_DIR/configs.py" ]; then
        print_ok "configs.py 存在"
        $PYTHON -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
exec(open('$SCRIPT_DIR/configs.py').read())
print(f'  WebUI 端口: {port}')
print(f'  API 端口: {api_port}')
print(f'  LLM 模式: {mode}')
print(f'  LLM 模型: {model_path}')
print(f'  SSL 证书: {ssl_certfile}')
" 2>&1
    else
        print_fail "configs.py 缺失"
    fi
}

# ============================================================
# Step 7: 端口检查
# ============================================================
step7_check_ports() {
    print_step 7 "端口检查"

    local ports=(6006 7871)
    local services=("WebUI (Gradio)" "API (FastAPI)")

    for i in "${!ports[@]}"; do
        local port=${ports[$i]}
        local service=${services[$i]}
        if command -v lsof &>/dev/null; then
            if lsof -i ":$port" &>/dev/null; then
                print_warn "端口 $port 被占用 ($service)"
            else
                print_ok "端口 $port 可用 ($service)"
            fi
        elif command -v netstat &>/dev/null; then
            if netstat -tlnp 2>/dev/null | grep -q ":$port "; then
                print_warn "端口 $port 被占用 ($service)"
            else
                print_ok "端口 $port 可用 ($service)"
            fi
        else
            print_info "端口 $port ($service) — 无法检测，请手动确认"
        fi
    done
}

# ============================================================
# Step 8: 启动服务
# ============================================================
step8_launch() {
    print_step 8 "启动 Linly-Talker"

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║           🎭 部署完成！选择启动模式:                        ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════════╝${NC}"

    echo -e "\n${BOLD}可用启动命令:${NC}\n"

    echo -e "  ${CYAN}[1] WebUI 全功能版 (推荐)${NC}"
    echo -e "  python webui.py"
    echo -e "  → 启动地址: http://localhost:6006\n"

    echo -e "  ${CYAN}[2] 基础对话版${NC}"
    echo -e "  python app.py"
    echo -e "  → 启动地址: http://localhost:7860\n"

    echo -e "  ${CYAN}[3] MuseTalk 实时对话${NC}"
    echo -e "  python app_musetalk.py"
    echo -e "  → 启动地址: http://localhost:7860\n"

    echo -e "  ${CYAN}[4] 语音+图片生成${NC}"
    echo -e "  python app_talk.py"
    echo -e "  → 启动地址: http://localhost:7860\n"

    echo -e "  ${CYAN}[5] FastAPI 接口${NC}"
    echo -e "  python LLM/Linly-api-fast.py"
    echo -e "  → API 地址: http://127.0.0.1:7871\n"

    echo -e "${BOLD}项目信息:${NC}"
    echo -e "  📁 项目路径: $SCRIPT_DIR"
    echo -e "  🌐 GitHub: https://github.com/Kedreamix/Linly-Talker"
    echo -e "  📚 文档: $SCRIPT_DIR/docs/"
    echo -e "  🎬 示例: $SCRIPT_DIR/examples/"
    echo -e "  📊 结果: $SCRIPT_DIR/results/"

    echo -e "\n${BOLD}技术栈:${NC}"
    echo -e "  🤖 LLM: Qwen-1.8B-Chat / ChatGLM / Gemini / GPT4Free"
    echo -e "  🎙️ ASR: FunASR / Whisper / OmniSenseVoice"
    echo -e "  🗣️ TTS: Edge-TTS / PaddleTTS / GPT-SoVITS / CosyVoice"
    echo -e "  👤 THG: SadTalker / Wav2Lip / MuseTalk / NeRFTalk"
    echo -e "  🖼️ 增强: GFPGAN"

    echo -e "\n${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}🎭 准备就绪！输入以下命令启动:${NC}"
    echo -e "  ${CYAN}cd $SCRIPT_DIR && python webui.py${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}\n"
}

# ============================================================
# 主流程
# ============================================================
main() {
    print_banner
    echo -e "${CYAN}开始部署 Linly-Talker 数字人智能对话系统...${NC}\n"

    step1_check_system
    step2_verify_project
    step3_verify_models
    step4_install_deps
    step5_optional_components
    step6_check_config
    step7_check_ports
    step8_launch
}

main "$@"
