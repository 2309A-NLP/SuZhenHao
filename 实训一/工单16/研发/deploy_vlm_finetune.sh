#!/bin/bash
# ============================================================================
# RAGFlow VLM 微调系统 一键部署脚本 v3.0
# ============================================================================
# 项目：工单16 — 基于 Qwen2-VL-2B-Instruct 的专利图纸问答 VLM 微调
# 版本：v3.0.0
# 适用环境：Linux / WSL2 Ubuntu 22.04+
# 硬件要求：NVIDIA GPU（推荐 RTX 4060 8GB 及以上）
# Python：3.10+
# 生成时间：2026年6月23日
# ============================================================================
#
# 一键部署流程：
#   chmod +x deploy_vlm_finetune.sh
#   ./deploy_vlm_finetune.sh              # 完整部署（环境检查→依赖→图片→数据集→配置→提示训练）
#
# 分步执行：
#   ./deploy_vlm_finetune.sh --check      # 仅检查系统环境
#   ./deploy_vlm_finetune.sh --install    # 仅安装 Python 依赖
#   ./deploy_vlm_finetune.sh --extract    # 仅从 PDF 提取页面图片
#   ./deploy_vlm_finetune.sh --dataset    # 仅构建 VLM 微调数据集
#   ./deploy_vlm_finetune.sh --train      # 仅启动训练（WebUI）
#   ./deploy_vlm_finetune.sh --evaluate   # 仅运行效果评估
#   ./deploy_vlm_finetune.sh --status     # 查看当前环境状态
#   ./deploy_vlm_finetune.sh --help       # 显示帮助信息
# ============================================================================

set -euo pipefail

# ============================================================================
# 全局配置 — 按实际环境修改
# ============================================================================
SCRIPT_VERSION="3.0.0"

# ---------- 模型配置 ----------
BASE_MODEL="Qwen2-VL-2B-Instruct"
BASE_MODEL_PATH="/home/su/llamafactory_env/models/${BASE_MODEL}"
LORA_SAVE_DIR="/home/su/ragflow_vlm_data/saves"

# ---------- 数据路径 ----------
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_ROOT="/home/su/ragflow_vlm_data"
PDF_DIR="/mnt/c/Users/23672/Desktop/RAG 新工单/14-17附件/original_problems/documents"
QUESTIONS_FILE="/mnt/c/Users/23672/Desktop/RAG 新工单/14-17附件/original_problems/questions.jsonl"
IMAGE_DIR="${DATA_ROOT}/images"
DATASET_DIR="${DATA_ROOT}/dataset"

# ---------- 图片提取参数 ----------
DPI=200                       # PDF 渲染分辨率，200 DPI 平衡质量与大小
MAX_WORKERS=4                 # 并行提取进程数

# ---------- 数据集参数 ----------
TRAIN_RATIO=0.8               # 训练集占比
VAL_RATIO=0.1                 # 验证集占比
TEST_RATIO=0.1                # 测试集占比
RANDOM_SEED=42                # 随机种子，保证可复现

# ---------- 训练参数 ----------
LORA_RANK=16                  # LoRA 低秩分解秩
LORA_ALPHA=32                 # LoRA 缩放因子（通常为 rank 的 2 倍）
LORA_TARGET="all"             # 对所有线性层应用 LoRA
LORA_DROPOUT=0.05             # LoRA dropout 率
CUTOFF_LEN=600                # 输入序列最大长度（图片 token ~280 + 文本）
BATCH_SIZE=1                  # 每 GPU batch 大小
GRAD_ACCUM=8                  # 梯度累积步数（等效 batch = 1×8 = 8）
LEARNING_RATE="1e-4"          # 学习率
MAX_STEPS=250                 # 最大训练步数
WARMUP_STEPS=10               # 预热步数

# ---------- LLaMA-Factory ----------
LLAMAFACTORY_VENV="/home/su/llamafactory_env"
WEBUI_PORT=7860
WEBUI_HOST="0.0.0.0"

# ---------- 评估参数 ----------
EVAL_MAX_SAMPLES=300          # 评估抽样数
EVAL_MAX_NEW_TOKENS=50        # 最大生成 token 数

# ---------- 操作模式 ----------
ACTION="deploy"

# ============================================================================
# 颜色与日志工具
# ============================================================================
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BOLD='\033[1m'
DIM='\033[2m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }
log_step()    { echo -e "\n${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
                echo -e "${CYAN}${BOLD}  Step $1${NC}"
                echo -e "${CYAN}${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"; }
log_success() { echo -e "${GREEN}${BOLD}✅ $1${NC}"; }
log_banner()  { echo -e "${MAGENTA}${BOLD}$1${NC}"; }
log_kv()      { printf "  ${DIM}%-20s${NC} %s\n" "$1" "$2"; }

# ============================================================================
# Step 1/8 — 检查系统环境
# ============================================================================
check_system() {
    log_step "1/8 — 检查系统环境"

    # 基础信息
    log_info "操作系统: $(uname -s) $(uname -r)"
    log_info "CPU 核心: $(nproc 2>/dev/null || echo unknown)"

    # 内存检查
    local total_mem_kb=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}')
    local total_mem_gb=$((total_mem_kb / 1024 / 1024))
    log_info "系统内存: ${total_mem_gb} GB"
    if [[ "$total_mem_gb" -lt 16 ]]; then
        log_warn "内存少于 16 GB，训练时可能需要更多 swap 空间"
    fi

    # 磁盘检查
    local disk_avail=$(df -BG "${HOME}" 2>/dev/null | tail -1 | awk '{print $4}' | tr -d 'G')
    log_info "可用磁盘: ${disk_avail} GB"
    if [[ "$disk_avail" -lt 50 ]]; then
        log_warn "磁盘少于 50 GB，建议至少 50 GB（模型权重 + 数据集 + checkpoint）"
    fi

    # GPU 检查
    echo ""
    if command -v nvidia-smi &>/dev/null; then
        log_info "GPU 信息:"
        nvidia-smi --query-gpu=name,memory.total,memory.used,driver_version --format=csv,noheader 2>/dev/null | while read line; do
            echo -e "  ${GREEN}▸${NC} $line"
        done

        # 检查 GPU 显存
        local gpu_mem=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null | head -1 | awk '{print $1}')
        if [[ -n "$gpu_mem" && "$gpu_mem" -lt 7000 ]]; then
            log_warn "GPU 显存不足 7GB，训练可能 OOM"
        fi
    else
        log_error "nvidia-smi 未找到！请安装 NVIDIA 驱动"
        return 1
    fi

    # CUDA 检查
    if command -v nvcc &>/dev/null; then
        local cuda_ver=$(nvcc --version 2>/dev/null | grep release | awk '{print $6}')
        log_info "CUDA Toolkit: ${cuda_ver}"
    else
        log_warn "CUDA Toolkit (nvcc) 未找到，不影响推理但可能影响编译"
    fi

    # Python 检查
    if command -v python3 &>/dev/null; then
        log_info "Python: $(python3 --version 2>&1)"
    else
        log_error "Python3 未安装！"
        return 1
    fi

    # 虚拟环境检查
    echo ""
    if [[ -d "${LLAMAFACTORY_VENV}" ]]; then
        log_success "LLaMA-Factory 虚拟环境: ${LLAMAFACTORY_VENV}"
    else
        log_warn "虚拟环境不存在: ${LLAMAFACTORY_VENV}"
        log_info "请先创建: python3 -m venv ${LLAMAFACTORY_VENV}"
    fi

    # 模型检查
    if [[ -d "${BASE_MODEL_PATH}" ]]; then
        local model_size=$(du -sh "${BASE_MODEL_PATH}" 2>/dev/null | awk '{print $1}')
        log_success "基座模型: ${BASE_MODEL} (${model_size})"
    else
        log_warn "基座模型未下载: ${BASE_MODEL_PATH}"
        log_info "下载命令: huggingface-cli download Qwen/Qwen2-VL-2B-Instruct --local-dir ${BASE_MODEL_PATH}"
    fi

    # 核心依赖检查
    echo ""
    local deps_ok=true

    if [[ -d "${LLAMAFACTORY_VENV}" ]]; then
        source "${LLAMAFACTORY_VENV}/bin/activate" 2>/dev/null || true

        for pkg in fitz bitsandbytes peft transformers torch llamafactory; do
            if python3 -c "import ${pkg}" 2>/dev/null; then
                local ver=$(python3 -c "import ${pkg}; print(getattr(${pkg}, '__version__', 'ok'))" 2>/dev/null)
                log_success "依赖 ${pkg}: ${ver}"
            else
                log_warn "依赖缺失: ${pkg}"
                deps_ok=false
            fi
        done
    fi

    if [[ "$deps_ok" == "false" ]]; then
        log_warn "部分依赖缺失，请运行: $0 --install"
    fi

    log_success "系统环境检查完成"
}

# ============================================================================
# Step 2/8 — 安装 Python 依赖
# ============================================================================
install_dependencies() {
    log_step "2/8 — 安装 Python 依赖"

    # 激活虚拟环境
    if [[ ! -d "${LLAMAFACTORY_VENV}" ]]; then
        log_error "虚拟环境不存在: ${LLAMAFACTORY_VENV}"
        log_info "请先创建虚拟环境:"
        log_info "  python3 -m venv ${LLAMAFACTORY_VENV}"
        log_info "  source ${LLAMAFACTORY_VENV}/bin/activate"
        log_info "  pip install llamafactory"
        return 1
    fi

    source "${LLAMAFACTORY_VENV}/bin/activate"
    log_info "已激活虚拟环境: ${LLAMAFACTORY_VENV}"

    # 逐个安装并验证
    local packages=(
        "PyMuPDF:fitz:PDF 页面渲染库"
        "bitsandbytes:bitsandbytes:4-bit 量化库"
        "peft:peft:LoRA 微调库"
        "Pillow:PIL:图片处理库"
    )

    for entry in "${packages[@]}"; do
        IFS=':' read -r pip_name import_name desc <<< "$entry"
        if python3 -c "import ${import_name}" 2>/dev/null; then
            log_success "${desc} (${pip_name}) — 已安装"
        else
            log_info "安装 ${desc} (${pip_name})..."
            pip install "${pip_name}" -q 2>/dev/null
            if python3 -c "import ${import_name}" 2>/dev/null; then
                log_success "${desc} (${pip_name}) — 安装成功"
            else
                log_error "${desc} (${pip_name}) — 安装失败"
            fi
        fi
    done

    # 验证 LLaMA-Factory
    if python3 -c "import llamafactory" 2>/dev/null; then
        log_success "LLaMA-Factory — 已安装"
    else
        log_warn "LLaMA-Factory 未找到，可能需要手动安装"
    fi

    # 验证 bitsandbytes CUDA 兼容性
    log_info "验证 bitsandbytes CUDA 兼容性..."
    if python3 -c "
import bitsandbytes as bnb
print(f'  bitsandbytes {bnb.__version__} loaded successfully')
" 2>/dev/null; then
        log_success "bitsandbytes CUDA 兼容性验证通过"
    else
        log_warn "bitsandbytes 可能与当前 CUDA 版本不兼容"
        log_info "请参考: https://github.com/TimDettmers/bitsandbytes"
    fi

    log_success "依赖安装完成"
}

# ============================================================================
# Step 3/8 — 检查原始数据
# ============================================================================
check_source_data() {
    log_step "3/8 — 检查原始数据"

    # 检查 questions.jsonl
    if [[ -f "${QUESTIONS_FILE}" ]]; then
        local q_count=$(wc -l < "${QUESTIONS_FILE}")
        log_success "问题文件: ${QUESTIONS_FILE} (${q_count} 条)"
    else
        log_error "问题文件不存在: ${QUESTIONS_FILE}"
        return 1
    fi

    # 检查 PDF 目录
    if [[ -d "${PDF_DIR}" ]]; then
        local pdf_count=$(find "${PDF_DIR}" -name "*.pdf" 2>/dev/null | wc -l)
        log_success "PDF 目录: ${PDF_DIR} (${pdf_count} 份文档)"
    else
        log_error "PDF 目录不存在: ${PDF_DIR}"
        return 1
    fi

    # 统计题目类型分布
    echo ""
    log_info "题目类型分布:"
    python3 -c "
import json
groups = {'1': 0, '2': 0, '3': 0, 'other': 0}
with open('${QUESTIONS_FILE}', 'r') as f:
    for line in f:
        item = json.loads(line.strip())
        g = str(item.get('group', 'other'))
        if g in groups:
            groups[g] += 1
        else:
            groups['other'] += 1
print(f'  Group 1 (文本理解): {groups[\"1\"]}')
print(f'  Group 2 (图纸位置): {groups[\"2\"]}')
print(f'  Group 3 (图纸推理): {groups[\"3\"]}')
print(f'  总计: {sum(groups.values())}')
" 2>/dev/null || log_warn "无法解析题目类型分布"

    log_success "原始数据检查完成"
}

# ============================================================================
# Step 4/8 — 从专利 PDF 提取页面图片
# ============================================================================
extract_images() {
    log_step "4/8 — 从专利 PDF 提取页面图片"

    # 检查输入
    if [[ ! -f "${QUESTIONS_FILE}" ]]; then
        log_error "问题文件不存在: ${QUESTIONS_FILE}"
        return 1
    fi
    if [[ ! -d "${PDF_DIR}" ]]; then
        log_error "PDF 目录不存在: ${PDF_DIR}"
        return 1
    fi

    # 检查是否已有图片
    if [[ -d "${IMAGE_DIR}" ]]; then
        local existing=$(find "${IMAGE_DIR}" -name "*.png" 2>/dev/null | wc -l)
        if [[ "$existing" -gt 0 ]]; then
            log_info "已存在 ${existing} 张图片，跳过提取"
            log_info "如需重新提取，请执行: rm -rf ${IMAGE_DIR}"
            return 0
        fi
    fi

    mkdir -p "${IMAGE_DIR}"

    # 统计信息
    local total_questions=$(wc -l < "${QUESTIONS_FILE}")
    log_info "问题总数: ${total_questions}"
    log_info "PDF 目录: ${PDF_DIR}"
    log_info "输出目录: ${IMAGE_DIR}"
    log_info "渲染参数: DPI=${DPI}, 并行进程=${MAX_WORKERS}"

    # 执行提取
    if [[ -f "${PROJECT_DIR}/extract_images.py" ]]; then
        log_info "运行 extract_images.py..."
        source "${LLAMAFACTORY_VENV}/bin/activate" 2>/dev/null || true
        python3 "${PROJECT_DIR}/extract_images.py"
    else
        log_error "未找到 extract_images.py"
        log_info "请将 extract_images.py 放在 ${PROJECT_DIR} 目录下"
        return 1
    fi

    # 验证结果
    local result_count=$(find "${IMAGE_DIR}" -name "*.png" 2>/dev/null | wc -l)
    local result_size=$(du -sh "${IMAGE_DIR}" 2>/dev/null | awk '{print $1}')
    log_success "图片提取完成: 共 ${result_count} 张, 总大小 ${result_size}"
}

# ============================================================================
# Step 5/8 — 构建 VLM 微调数据集
# ============================================================================
build_dataset() {
    log_step "5/8 — 构建 VLM 微调数据集"

    # 检查图片目录
    if [[ ! -d "${IMAGE_DIR}" ]]; then
        log_error "图片目录不存在: ${IMAGE_DIR}"
        log_info "请先运行图片提取步骤: $0 --extract"
        return 1
    fi

    local image_count=$(find "${IMAGE_DIR}" -name "*.png" 2>/dev/null | wc -l)
    log_info "已有图片: ${image_count} 张"

    # 检查是否已有数据集
    if [[ -f "${DATASET_DIR}/train.jsonl" ]]; then
        local train_count=$(wc -l < "${DATASET_DIR}/train.jsonl")
        log_info "数据集已存在: train=${train_count} 条"
        log_info "如需重新构建，请执行: rm -rf ${DATASET_DIR}"
        return 0
    fi

    mkdir -p "${DATASET_DIR}"

    # 执行构建
    if [[ -f "${PROJECT_DIR}/build_dataset.py" ]]; then
        log_info "运行 build_dataset.py..."
        source "${LLAMAFACTORY_VENV}/bin/activate" 2>/dev/null || true
        python3 "${PROJECT_DIR}/build_dataset.py"
    else
        log_error "未找到 build_dataset.py"
        return 1
    fi

    # 验证结果
    echo ""
    log_info "数据集统计:"
    for split in train val test; do
        if [[ -f "${DATASET_DIR}/${split}.jsonl" ]]; then
            local count=$(wc -l < "${DATASET_DIR}/${split}.jsonl")
            log_success "  ${split}.jsonl: ${count} 条"
        fi
    done

    if [[ -f "${DATASET_DIR}/dataset_info.json" ]]; then
        log_success "  dataset_info.json: LLaMA-Factory 注册配置"
    fi

    log_success "数据集构建完成"
}

# ============================================================================
# Step 6/8 — 配置 QLoRA 训练参数
# ============================================================================
configure_training() {
    log_step "6/8 — 配置 QLoRA 训练参数"

    # 创建 DeepSpeed 缓存目录
    mkdir -p "${PROJECT_DIR}/llamaboard_cache"

    # ---- DeepSpeed ZeRO Stage 2 ----
    cat > "${PROJECT_DIR}/llamaboard_cache/ds_z2_config.json" << 'EOF'
{
  "train_micro_batch_size_per_gpu": "auto",
  "gradient_accumulation_steps": "auto",
  "gradient_clipping": "auto",
  "steps_per_print": 100,
  "zero_optimization": {
    "stage": 2,
    "offload_optimizer": { "device": "none", "pin_memory": true },
    "allgather_partitions": true,
    "allgather_bucket_size": 2e8,
    "reduce_scatter": true,
    "reduce_bucket_size": 2e8,
    "overlap_comm": false,
    "contiguous_gradients": true
  },
  "bf16": { "enabled": "auto" },
  "optimizer": {
    "type": "AdamW",
    "params": { "lr": "auto", "betas": "auto", "eps": "auto", "weight_decay": "auto" }
  },
  "scheduler": {
    "type": "WarmupDecayLR",
    "params": { "warmup_min_lr": "auto", "warmup_max_lr": "auto", "warmup_num_steps": "auto", "total_num_steps": "auto" }
  }
}
EOF

    # ---- DeepSpeed ZeRO Stage 2 + CPU Offload（推荐） ----
    cat > "${PROJECT_DIR}/llamaboard_cache/ds_z2_offload_config.json" << 'EOF'
{
  "train_micro_batch_size_per_gpu": "auto",
  "gradient_accumulation_steps": "auto",
  "gradient_clipping": "auto",
  "steps_per_print": 100,
  "zero_optimization": {
    "stage": 2,
    "offload_optimizer": { "device": "cpu", "pin_memory": true },
    "allgather_partitions": true,
    "allgather_bucket_size": 2e8,
    "reduce_scatter": true,
    "reduce_bucket_size": 2e8,
    "overlap_comm": false,
    "contiguous_gradients": true
  },
  "bf16": { "enabled": "auto" },
  "optimizer": {
    "type": "AdamW",
    "params": { "lr": "auto", "betas": "auto", "eps": "auto", "weight_decay": "auto" }
  },
  "scheduler": {
    "type": "WarmupDecayLR",
    "params": { "warmup_min_lr": "auto", "warmup_max_lr": "auto", "warmup_num_steps": "auto", "total_num_steps": "auto" }
  }
}
EOF

    # ---- DeepSpeed ZeRO Stage 3 ----
    cat > "${PROJECT_DIR}/llamaboard_cache/ds_z3_config.json" << 'EOF'
{
  "train_micro_batch_size_per_gpu": "auto",
  "gradient_accumulation_steps": "auto",
  "gradient_clipping": "auto",
  "steps_per_print": 100,
  "zero_optimization": {
    "stage": 3,
    "offload_optimizer": { "device": "none", "pin_memory": true },
    "offload_param": { "device": "none", "pin_memory": true },
    "overlap_comm": true,
    "contiguous_gradients": true,
    "sub_group_size": 1e9,
    "reduce_bucket_size": "auto",
    "stage3_prefetch_bucket_size": "auto",
    "stage3_param_persistence_threshold": "auto",
    "stage3_max_live_parameters": 1e9,
    "stage3_max_reuse_distance": 1e9,
    "stage3_gather_16bit_weights_on_model_save": true
  },
  "bf16": { "enabled": "auto" },
  "optimizer": {
    "type": "AdamW",
    "params": { "lr": "auto", "betas": "auto", "eps": "auto", "weight_decay": "auto" }
  },
  "scheduler": {
    "type": "WarmupDecayLR",
    "params": { "warmup_min_lr": "auto", "warmup_max_lr": "auto", "warmup_num_steps": "auto", "total_num_steps": "auto" }
  }
}
EOF

    # ---- DeepSpeed ZeRO Stage 3 + CPU Offload ----
    cat > "${PROJECT_DIR}/llamaboard_cache/ds_z3_offload_config.json" << 'EOF'
{
  "train_micro_batch_size_per_gpu": "auto",
  "gradient_accumulation_steps": "auto",
  "gradient_clipping": "auto",
  "steps_per_print": 100,
  "zero_optimization": {
    "stage": 3,
    "offload_optimizer": { "device": "cpu", "pin_memory": true },
    "offload_param": { "device": "cpu", "pin_memory": true },
    "overlap_comm": true,
    "contiguous_gradients": true,
    "sub_group_size": 1e9,
    "reduce_bucket_size": "auto",
    "stage3_prefetch_bucket_size": "auto",
    "stage3_param_persistence_threshold": "auto",
    "stage3_max_live_parameters": 1e9,
    "stage3_max_reuse_distance": 1e9,
    "stage3_gather_16bit_weights_on_model_save": true
  },
  "bf16": { "enabled": "auto" },
  "optimizer": {
    "type": "AdamW",
    "params": { "lr": "auto", "betas": "auto", "eps": "auto", "weight_decay": "auto" }
  },
  "scheduler": {
    "type": "WarmupDecayLR",
    "params": { "warmup_min_lr": "auto", "warmup_max_lr": "auto", "warmup_num_steps": "auto", "total_num_steps": "auto" }
  }
}
EOF

    # ---- 生成 QLoRA 训练配置 v3 ----
    cat > "${PROJECT_DIR}/qlora_config_v3.yaml" << EOF
### 工单16 - QLoRA 微调配置 v3
### Qwen2-VL-2B-Instruct + RTX 4060 8GB 适配

model: ${BASE_MODEL_PATH}
model_class: qwen2_vl
template: qwen2_vl

# PEFT (LoRA) 配置
peft_config:
  name: lora
  r: ${LORA_RANK}
  lora_alpha: ${LORA_ALPHA}
  lora_dropout: ${LORA_DROPOUT}
  target_modules: ${LORA_TARGET}

# 量化配置
quant_config:
  name: bnb
  quantization_bit: 4

# 分布式配置
dist_config:
  name: none

# 数据配置
train_dataset: data/v1_sft_demo.yaml

# 训练参数
output_dir: ${LORA_SAVE_DIR}
micro_batch_size: ${BATCH_SIZE}
gradient_accumulation_steps: ${GRAD_ACCUM}
cutoff_len: ${CUTOFF_LEN}
learning_rate: ${LEARNING_RATE}
max_steps: ${MAX_STEPS}
lr_scheduler_type: cosine
warmup_steps: ${WARMUP_STEPS}
weight_decay: 0.01
bf16: true
gradient_checkpointing: true
logging_steps: 5
save_steps: 500
save_total_limit: 2
eval_strategy: "no"
preprocessing_num_workers: 4
seed: ${RANDOM_SEED}
EOF

    # ---- 生成 launch_webui.sh ----
    cat > "${PROJECT_DIR}/launch_webui.sh" << LAUNCH_EOF
#!/bin/bash
# 启动 LLaMA-Factory WebUI (LlamaBoard)
echo "=========================================="
echo "  启动 LLaMA-Factory WebUI (LlamaBoard)"
echo "  访问地址: http://localhost:${WEBUI_PORT}"
echo "=========================================="
source ${LLAMAFACTORY_VENV}/bin/activate
llamafactory-cli webui --host ${WEBUI_HOST} --port ${WEBUI_PORT}
LAUNCH_EOF
    chmod +x "${PROJECT_DIR}/launch_webui.sh"

    log_success "训练配置完成"

    # 打印配置摘要
    echo ""
    echo -e "  ${BOLD}📋 QLoRA 训练参数摘要${NC}"
    echo -e "  ├─ 基座模型:       ${BASE_MODEL} (2B 参数)"
    echo -e "  ├─ 量化方式:       4-bit NF4 (bitsandbytes)"
    echo -e "  ├─ LoRA rank:      ${LORA_RANK}"
    echo -e "  ├─ LoRA alpha:     ${LORA_ALPHA}"
    echo -e "  ├─ LoRA target:    ${LORA_TARGET} (所有线性层)"
    echo -e "  ├─ LoRA dropout:   ${LORA_DROPOUT}"
    echo -e "  ├─ cutoff_len:     ${CUTOFF_LEN}"
    echo -e "  ├─ batch_size:     ${BATCH_SIZE} (grad_accum=${GRAD_ACCUM}, effective=${GRAD_ACCUM})"
    echo -e "  ├─ learning_rate:  ${LEARNING_RATE}"
    echo -e "  ├─ max_steps:      ${MAX_STEPS}"
    echo -e "  ├─ warmup_steps:   ${WARMUP_STEPS}"
    echo -e "  ├─ 可训练参数:     ~3000 万 (~1.5%)"
    echo -e "  └─ 预计显存占用:   3-4 GB"
    echo ""
    echo -e "  ${BOLD}📋 DeepSpeed 配置${NC}"
    echo -e "  └─ RTX 4060 8GB → 推荐 ZeRO Stage 2 + CPU Offload"
}

# ============================================================================
# Step 7/8 — 启动训练
# ============================================================================
start_training() {
    log_step "7/8 — 启动 QLoRA 微调训练"

    # 前置检查
    if [[ ! -f "${DATASET_DIR}/train.jsonl" ]]; then
        log_error "训练数据集不存在: ${DATASET_DIR}/train.jsonl"
        log_info "请先运行: $0 --dataset"
        return 1
    fi

    if [[ ! -d "${BASE_MODEL_PATH}" ]]; then
        log_error "基座模型不存在: ${BASE_MODEL_PATH}"
        return 1
    fi

    local train_count=$(wc -l < "${DATASET_DIR}/train.jsonl")
    log_info "训练集: ${train_count} 条"
    log_info "基座模型: ${BASE_MODEL_PATH}"
    log_info "LoRA 保存目录: ${LORA_SAVE_DIR}"

    mkdir -p "${LORA_SAVE_DIR}"

    # 启动 WebUI
    echo ""
    log_info "启动 LLaMA-Factory WebUI..."
    echo ""
    echo -e "  ${BOLD}📌 WebUI 操作步骤:${NC}"
    echo -e "  ┌─────────────────────────────────────────────────────────────┐"
    echo -e "  │ 1. 浏览器打开 http://localhost:${WEBUI_PORT}                    │"
    echo -e "  │ 2. 模型选择: ${BASE_MODEL_PATH}         │"
    echo -e "  │ 3. 数据集选择: vlm_industrial_qa_train                      │"
    echo -e "  │ 4. LoRA 参数: rank=${LORA_RANK}, alpha=${LORA_ALPHA}, target=${LORA_TARGET}       │"
    echo -e "  │ 5. 量化方式: 4-bit NF4 (bitsandbytes)                      │"
    echo -e "  │ 6. 训练参数: cutoff=${CUTOFF_LEN}, batch=${BATCH_SIZE}, grad_acc=${GRAD_ACCUM}        │"
    echo -e "  │ 7. 学习率: ${LEARNING_RATE}, steps=${MAX_STEPS}, warmup=${WARMUP_STEPS}                 │"
    echo -e "  │ 8. DeepSpeed: ZeRO Stage 2 + CPU Offload                   │"
    echo -e "  │ 9. 点击「开始训练」按钮                                     │"
    echo -e "  └─────────────────────────────────────────────────────────────┘"
    echo ""

    source "${LLAMAFACTORY_VENV}/bin/activate" 2>/dev/null || true
    llamafactory-cli webui --host "${WEBUI_HOST}" --port "${WEBUI_PORT}"
}

# ============================================================================
# Step 8/8 — 运行效果评估
# ============================================================================
run_evaluation() {
    log_step "8/8 — 运行微调效果评估"

    # 前置检查
    if [[ ! -f "${DATASET_DIR}/test.jsonl" ]]; then
        log_error "测试数据集不存在: ${DATASET_DIR}/test.jsonl"
        return 1
    fi

    if [[ ! -d "${LORA_SAVE_DIR}" ]]; then
        log_error "LoRA 权重目录不存在: ${LORA_SAVE_DIR}"
        log_info "请先完成训练: $0 --train"
        return 1
    fi

    # 查找最新的 LoRA 权重
    local latest_lora=$(find "${LORA_SAVE_DIR}" -name "adapter_config.json" -printf '%T@ %h\n' 2>/dev/null | sort -rn | head -1 | awk '{print $2}')
    if [[ -z "$latest_lora" ]]; then
        log_error "未找到 LoRA 适配器权重"
        log_info "请先完成训练"
        return 1
    fi
    log_info "LoRA 权重: ${latest_lora}"
    log_info "测试集: ${DATASET_DIR}/test.jsonl"
    log_info "抽样数: ${EVAL_MAX_SAMPLES}"

    # 运行评估
    if [[ -f "${PROJECT_DIR}/evaluate.py" ]]; then
        echo ""
        log_info "运行 evaluate.py（可能需要几分钟）..."
        source "${LLAMAFACTORY_VENV}/bin/activate" 2>/dev/null || true
        python3 "${PROJECT_DIR}/evaluate.py"
    else
        log_error "未找到 evaluate.py"
        return 1
    fi

    # 展示结果
    echo ""
    if [[ -f "${PROJECT_DIR}/evaluation_report.json" ]]; then
        log_success "评估完成！"
        echo -e "  ${BOLD}📊 评估报告:${NC} ${PROJECT_DIR}/evaluation_report.json"
        echo -e "  ${BOLD}📊 错误分析:${NC} ${PROJECT_DIR}/error_analysis.json"

        # 尝试解析结果
        python3 -c "
import json
with open('${PROJECT_DIR}/evaluation_report.json') as f:
    r = json.load(f)
base_acc = r['base_model']['accuracy']
ft_acc = r['fine_tuned_model']['accuracy']
improve = r['improvement']
print()
print(f'  ┌────────────────────────────────────────┐')
print(f'  │  📊 评估结果摘要                        │')
print(f'  ├────────────────────────────────────────┤')
print(f'  │  基座模型准确率:  {base_acc:>6.1f}%               │')
print(f'  │  微调模型准确率:  {ft_acc:>6.1f}%               │')
print(f'  │  绝对提升:        {improve:>+6.1f}%               │')
print(f'  └────────────────────────────────────────┘')
" 2>/dev/null || true
    fi
}

# ============================================================================
# 工具函数
# ============================================================================
show_status() {
    echo ""
    log_banner "╔══════════════════════════════════════════════════════════════╗"
    log_banner "║     📊 RAGFlow VLM 微调系统 — 环境状态                      ║"
    log_banner "╚══════════════════════════════════════════════════════════════╝"
    echo ""

    # GPU
    echo -e "  ${BOLD}🖥️  GPU 状态${NC}"
    if command -v nvidia-smi &>/dev/null; then
        nvidia-smi --query-gpu=name,memory.total,memory.used,memory.free,temperature.gpu --format=csv,noheader 2>/dev/null | while read line; do
            echo "    $line"
        done
    else
        echo "    nvidia-smi 不可用"
    fi

    # 虚拟环境
    echo -e "\n  ${BOLD}🐍 Python 环境${NC}"
    if [[ -d "${LLAMAFACTORY_VENV}" ]]; then
        echo -e "    ${GREEN}✓${NC} ${LLAMAFACTORY_VENV}"
        source "${LLAMAFACTORY_VENV}/bin/activate" 2>/dev/null
        echo -e "    Python: $(python3 --version 2>&1)"
    else
        echo -e "    ${RED}✗${NC} ${LLAMAFACTORY_VENV} 不存在"
    fi

    # 基座模型
    echo -e "\n  ${BOLD}📦 基座模型${NC}"
    if [[ -d "${BASE_MODEL_PATH}" ]]; then
        echo -e "    ${GREEN}✓${NC} ${BASE_MODEL} ($(du -sh "${BASE_MODEL_PATH}" 2>/dev/null | awk '{print $1}'))"
    else
        echo -e "    ${RED}✗${NC} ${BASE_MODEL} 未下载"
    fi

    # 原始数据
    echo -e "\n  ${BOLD}📄 原始数据${NC}"
    if [[ -f "${QUESTIONS_FILE}" ]]; then
        echo -e "    ${GREEN}✓${NC} questions.jsonl ($(wc -l < "${QUESTIONS_FILE}") 条)"
    else
        echo -e "    ${RED}✗${NC} questions.jsonl 不存在"
    fi
    if [[ -d "${PDF_DIR}" ]]; then
        echo -e "    ${GREEN}✓${NC} PDF 文档 ($(find "${PDF_DIR}" -name "*.pdf" 2>/dev/null | wc -l) 份)"
    else
        echo -e "    ${RED}✗${NC} PDF 目录不存在"
    fi

    # 处理后的数据
    echo -e "\n  ${BOLD}📁 处理数据${NC}"
    if [[ -d "${IMAGE_DIR}" ]]; then
        echo -e "    ${GREEN}✓${NC} 图片: $(find "${IMAGE_DIR}" -name "*.png" 2>/dev/null | wc -l) 张 ($(du -sh "${IMAGE_DIR}" 2>/dev/null | awk '{print $1}'))"
    else
        echo -e "    ${YELLOW}○${NC} 图片目录不存在（需运行 --extract）"
    fi
    for split in train val test; do
        if [[ -f "${DATASET_DIR}/${split}.jsonl" ]]; then
            echo -e "    ${GREEN}✓${NC} ${split}.jsonl: $(wc -l < "${DATASET_DIR}/${split}.jsonl") 条"
        else
            echo -e "    ${YELLOW}○${NC} ${split}.jsonl 不存在"
        fi
    done

    # 训练结果
    echo -e "\n  ${BOLD}🔧 训练结果${NC}"
    if [[ -d "${LORA_SAVE_DIR}" ]]; then
        local lora_count=$(find "${LORA_SAVE_DIR}" -name "adapter_config.json" 2>/dev/null | wc -l)
        echo -e "    ${GREEN}✓${NC} LoRA 权重: ${lora_count} 份"
    else
        echo -e "    ${YELLOW}○${NC} 未找到训练结果"
    fi

    # 评估
    echo -e "\n  ${BOLD}📊 评估结果${NC}"
    if [[ -f "${PROJECT_DIR}/evaluation_report.json" ]]; then
        echo -e "    ${GREEN}✓${NC} 评估报告存在"
        python3 -c "
import json
with open('${PROJECT_DIR}/evaluation_report.json') as f:
    r = json.load(f)
print(f'    基座: {r[\"base_model\"][\"accuracy\"]:.1f}% → 微调: {r[\"fine_tuned_model\"][\"accuracy\"]:.1f}% (提升 {r[\"improvement\"]:+.1f}%)')
" 2>/dev/null || true
    else
        echo -e "    ${YELLOW}○${NC} 未运行评估"
    fi

    # 项目文件
    echo -e "\n  ${BOLD}📂 项目文件${NC}"
    for f in extract_images.py build_dataset.py evaluate.py qlora_config.yaml qlora_config_v2.yaml qlora_config_v3.yaml deploy_vlm_finetune.sh launch_webui.sh; do
        if [[ -f "${PROJECT_DIR}/${f}" ]]; then
            echo -e "    ${GREEN}✓${NC} ${f}"
        else
            echo -e "    ${RED}✗${NC} ${f}"
        fi
    done
    echo ""
}

show_usage() {
    echo ""
    log_banner "RAGFlow VLM 微调部署脚本 v${SCRIPT_VERSION}"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  --check      检查系统环境（GPU、Python、依赖、模型）"
    echo "  --install    安装 Python 依赖"
    echo "  --extract    从专利 PDF 提取页面图片"
    echo "  --dataset    构建 VLM 微调数据集"
    echo "  --train      启动 QLoRA 训练（WebUI）"
    echo "  --evaluate   运行微调效果评估"
    echo "  --status     查看环境状态总览"
    echo "  --help       显示此帮助信息"
    echo ""
    echo "默认（无参数）: 执行完整部署流程"
    echo ""
    echo "示例:"
    echo "  $0                  # 完整部署"
    echo "  $0 --check          # 仅检查环境"
    echo "  $0 --status         # 查看状态"
    echo "  $0 --train          # 仅启动训练"
}

# ============================================================================
# 主流程
# ============================================================================
main() {
    echo ""
    log_banner "╔══════════════════════════════════════════════════════════════════╗"
    log_banner "║   🚀 RAGFlow VLM 微调系统 部署脚本 v${SCRIPT_VERSION}                       ║"
    log_banner "║   📦 ${BASE_MODEL} + QLoRA + LLaMA-Factory                     ║"
    log_banner "║   🖥️  RTX 4060 (8GB) + WSL2 Ubuntu                             ║"
    log_banner "╚══════════════════════════════════════════════════════════════════╝"
    echo ""

    # 解析命令行参数
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --check)    ACTION="check"; shift ;;
            --install)  ACTION="install"; shift ;;
            --extract)  ACTION="extract"; shift ;;
            --dataset)  ACTION="dataset"; shift ;;
            --train)    ACTION="train"; shift ;;
            --evaluate) ACTION="evaluate"; shift ;;
            --status)   ACTION="status"; shift ;;
            --help)     show_usage; exit 0 ;;
            *)          log_error "未知选项: $1"; show_usage; exit 1 ;;
        esac
    done

    # 执行对应操作
    case "$ACTION" in
        check)
            check_system
            ;;
        install)
            install_dependencies
            ;;
        extract)
            check_system
            check_source_data
            extract_images
            ;;
        dataset)
            check_system
            check_source_data
            build_dataset
            ;;
        train)
            check_system
            configure_training
            start_training
            ;;
        evaluate)
            check_system
            run_evaluation
            ;;
        status)
            show_status
            ;;
        deploy)
            log_info "执行完整部署流程..."
            echo ""
            check_system
            install_dependencies
            check_source_data
            extract_images
            build_dataset
            configure_training

            echo ""
            log_banner "╔══════════════════════════════════════════════════════════════╗"
            log_banner "║     🎉 部署环境准备完成！                                   ║"
            log_banner "╚══════════════════════════════════════════════════════════════╝"
            echo ""
            echo -e "  ${BOLD}📌 下一步 — 启动训练:${NC}"
            echo -e "     bash launch_webui.sh"
            echo -e "     # 或"
            echo -e "     $0 --train"
            echo ""
            echo -e "  ${BOLD}📌 训练完成后 — 运行评估:${NC}"
            echo -e "     $0 --evaluate"
            echo ""
            echo -e "  ${BOLD}📌 快捷命令:${NC}"
            echo -e "     $0 --status     查看环境状态"
            echo -e "     $0 --check      检查系统环境"
            echo ""
            ;;
    esac
}

main "$@"
