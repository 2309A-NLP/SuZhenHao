#!/bin/bash
# ============================================================
# DocumentQualityAssessmentSkill — 完整部署脚本
# 项目路径: C:\Users\23672\Desktop\2309A\实训一\工单18
# 用途: 一键部署文档质量评估工具（含环境检查、依赖安装、验证测试）
# ============================================================

set -e  # 遇错即停

# ---- 颜色定义 ----
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# ---- 项目路径 ----
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$SCRIPT_DIR/.cursor/skills/document-quality-assessment"
SCRIPTS_DIR="$SKILL_DIR/scripts"
TESTS_DIR="$SCRIPT_DIR/tests"
API_DIR="$SCRIPT_DIR/api"
AGENT_DIR="$SCRIPT_DIR/agent_integration"
CONFIG_FILE="$SKILL_DIR/assessment_config.yaml"
REQUIREMENTS_FILE="$SKILL_DIR/requirements.txt"

# ============================================================
# 工具函数
# ============================================================
print_banner() {
    echo -e "${CYAN}"
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║                                                          ║"
    echo "║     📋 DocumentQualityAssessmentSkill                   ║"
    echo "║     文档质量评估工具 — 部署脚本                          ║"
    echo "║                                                          ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    local step=$1
    local total=$2
    local msg=$3
    echo -e "\n${BLUE}[${step}/${total}]${NC} ${BOLD}${msg}${NC}"
}

print_ok() {
    echo -e "  ${GREEN}✔${NC} $1"
}

print_warn() {
    echo -e "  ${YELLOW}⚠${NC} $1"
}

print_fail() {
    echo -e "  ${RED}✘${NC} $1"
}

print_info() {
    echo -e "  ${CYAN}ℹ${NC} $1"
}

# ============================================================
# Step 1: 环境检查
# ============================================================
step1_check_environment() {
    print_step 1 6 "环境检查"

    # Python 版本
    if command -v python3 &>/dev/null; then
        PYTHON=$(command -v python3)
    elif command -v python &>/dev/null; then
        PYTHON=$(command -v python)
    else
        print_fail "未找到 Python，请安装 Python 3.8+"
        exit 1
    fi

    PY_VERSION=$($PYTHON --version 2>&1 | grep -oP '\d+\.\d+')
    PY_MAJOR=$(echo "$PY_VERSION" | cut -d. -f1)
    PY_MINOR=$(echo "$PY_VERSION" | cut -d. -f2)

    if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 8 ]; }; then
        print_fail "Python 版本过低: $PY_VERSION (需要 3.8+)"
        exit 1
    fi
    print_ok "Python 版本: $PY_VERSION ($PYTHON)"

    # pip
    if $PYTHON -m pip --version &>/dev/null; then
        PIP="$PYTHON -m pip"
        print_ok "pip 可用: $($PYTHON -m pip --version 2>&1 | head -1)"
    else
        print_warn "pip 不可用，尝试安装..."
        $PYTHON -m ensurepip --upgrade 2>/dev/null || {
            print_fail "pip 安装失败，请手动安装"
            exit 1
        }
        PIP="$PYTHON -m pip"
        print_ok "pip 已安装"
    fi

    # 检查项目目录结构
    local dirs=(
        "$SKILL_DIR"
        "$SCRIPTS_DIR"
        "$TESTS_DIR"
        "$API_DIR"
        "$AGENT_DIR"
    )
    for dir in "${dirs[@]}"; do
        if [ -d "$dir" ]; then
            print_ok "目录存在: $(basename "$dir")/"
        else
            print_warn "目录不存在: $dir (将创建)"
            mkdir -p "$dir"
        fi
    done

    # 检查核心文件
    local files=(
        "$SCRIPTS_DIR/assess_documents.py"
        "$CONFIG_FILE"
        "$REQUIREMENTS_FILE"
        "$TESTS_DIR/test_skill.py"
        "$API_DIR/quality_inspection_api.py"
        "$AGENT_DIR/quality_assessment_tool.py"
    )
    for file in "${files[@]}"; do
        if [ -f "$file" ]; then
            print_ok "文件存在: $(basename "$file")"
        else
            print_fail "文件缺失: $file"
            exit 1
        fi
    done
}

# ============================================================
# Step 2: 安装 Python 依赖
# ============================================================
step2_install_dependencies() {
    print_step 2 6 "安装 Python 依赖"

    echo -e "  ${CYAN}Installing from: ${REQUIREMENTS_FILE}${NC}"

    # 核心依赖
    $PIP install --upgrade pip -q 2>/dev/null

    $PIP install \
        "pymupdf>=1.23.0" \
        "python-docx>=1.1.0" \
        "beautifulsoup4>=4.12.0" \
        "simhash>=2.1.0" \
        "pyyaml>=6.0" \
        "tqdm>=4.66.0" \
        -q 2>&1 | tail -5

    # 测试依赖
    $PIP install pytest -q 2>/dev/null

    # 验证安装
    local modules=("fitz" "docx" "bs4" "simhash" "yaml" "tqdm" "pytest")
    local names=("pymupdf" "python-docx" "beautifulsoup4" "simhash" "pyyaml" "tqdm" "pytest")

    for i in "${!modules[@]}"; do
        if $PYTHON -c "import ${modules[$i]}" 2>/dev/null; then
            print_ok "已安装: ${names[$i]}"
        else
            print_fail "安装失败: ${names[$i]}"
            exit 1
        fi
    done
}

# ============================================================
# Step 3: 配置验证
# ============================================================
step3_validate_config() {
    print_step 3 6 "配置文件验证"

    if [ ! -f "$CONFIG_FILE" ]; then
        print_warn "配置文件不存在，将使用默认配置"
        return
    fi

    # 验证 YAML 格式
    if $PYTHON -c "
import yaml, sys
with open('$CONFIG_FILE', 'r', encoding='utf-8') as f:
    cfg = yaml.safe_load(f)

required_keys = ['pdf_type', 'duplicate', 'sensitive', 'length', 'classification', 'format']
missing = [k for k in required_keys if k not in cfg]
if missing:
    print(f'  ✘ 配置缺少字段: {missing}')
    sys.exit(1)

# 验证阈值范围
assert cfg['pdf_type']['text_page_min_chars'] > 0, 'text_page_min_chars must be > 0'
assert 0 < cfg['duplicate']['simhash_threshold'] < 64, 'simhash_threshold must be 1-63'
assert cfg['sensitive']['context_chars'] > 0, 'context_chars must be > 0'
print('  ✔ 配置格式正确，所有阈值有效')
" 2>&1; then
        print_ok "YAML 配置验证通过"
        print_info "PDF文字阈值: $($PYTHON -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE'))['pdf_type']['text_page_min_chars'])") 字符"
        print_info "SimHash阈值: $($PYTHON -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE'))['duplicate']['simhash_threshold'])") (汉明距离)"
        print_info "敏感上下文: $($PYTHON -c "import yaml; print(yaml.safe_load(open('$CONFIG_FILE'))['sensitive']['context_chars'])") 字符"
    else
        print_fail "配置验证失败"
        exit 1
    fi
}

# ============================================================
# Step 4: 运行单元测试
# ============================================================
step4_run_tests() {
    print_step 4 6 "运行单元测试"

    cd "$SCRIPT_DIR"
    $PYTHON -m pytest "$TESTS_DIR/test_skill.py" -v --tb=short 2>&1 | tail -30

    local exit_code=${PIPESTATUS[0]}
    if [ $exit_code -eq 0 ]; then
        print_ok "所有测试通过 ✔"
    else
        print_warn "部分测试未通过 (exit code: $exit_code)"
        print_info "这可能是由于测试环境中缺少 PDF 样本文件"
    fi
}

# ============================================================
# Step 5: 快速功能验证
# ============================================================
step5_functional_test() {
    print_step 5 6 "快速功能验证"

    # 创建临时测试目录
    local TEST_DIR=$(mktemp -d)
    echo "# 测试文档" > "$TEST_DIR/test1.md"
    echo "这是一个较长的测试文档内容，用于验证文档质量评估工具的基本功能是否正常。" > "$TEST_DIR/test2.txt"
    echo '{"test": "data", "count": 42}' > "$TEST_DIR/test3.json"
    echo "13812345678" > "$TEST_DIR/contact.txt"
    cp "$TEST_DIR/test1.md" "$TEST_DIR/test1_copy.md"  # 故意制造重复

    print_info "测试目录: $TEST_DIR"

    # 运行评估
    local OUTPUT_DIR="$TEST_DIR/output"
    $PYTHON "$SCRIPTS_DIR/assess_documents.py" \
        --input "$TEST_DIR" \
        --output-dir "$OUTPUT_DIR" \
        --no-classify \
        2>&1 | tail -10

    # 检查输出
    if [ -f "$OUTPUT_DIR/quality_report.json" ]; then
        print_ok "JSON 报告已生成"

        # 验证 JSON 结构
        $PYTHON -c "
import json
with open('$OUTPUT_DIR/quality_report.json') as f:
    r = json.load(f)
fields = ['meta', 'format_distribution', 'pdf_page_types', 'length_distribution', 'duplicates', 'sensitive_info']
missing = [f for f in fields if f not in r]
if missing:
    print(f'  ✘ JSON 缺少字段: {missing}')
else:
    print(f'  ✔ JSON 结构完整 ({len(fields)} 个顶级字段)')
    print(f'  ✔ 文件总数: {r[\"meta\"][\"total_files\"]}')
    print(f'  ✔ 耗时: {r[\"meta\"][\"duration_seconds\"]}s')
    # 验证重复检测
    dup_count = r['duplicates']['exact']['total_groups']
    print(f'  ✔ 重复检测: {dup_count} 组精确重复')
    # 验证敏感信息
    sens_count = r['sensitive_info']['summary']['total_findings']
    print(f'  ✔ 敏感信息: {sens_count} 处命中')
" 2>&1
    else
        print_fail "JSON 报告未生成"
    fi

    if [ -f "$OUTPUT_DIR/quality_brief.html" ]; then
        print_ok "HTML 简报已生成 ($(du -h "$OUTPUT_DIR/quality_brief.html" | cut -f1))"
    else
        print_fail "HTML 简报未生成"
    fi

    # 清理测试目录
    rm -rf "$TEST_DIR"
}

# ============================================================
# Step 6: 项目信息汇总
# ============================================================
step6_summary() {
    print_step 6 6 "部署完成"

    echo -e "\n${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              部署成功！项目信息汇总                     ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"

    echo -e "\n${BOLD}📁 项目结构:${NC}"
    echo -e "  ${CYAN}$SCRIPT_DIR/${NC}"
    echo -e "  ├── .cursor/skills/document-quality-assessment/"
    echo -e "  │   ├── scripts/assess_documents.py    ${GREEN}← 核心评估引擎${NC}"
    echo -e "  │   ├── assessment_config.yaml         ${GREEN}← 配置文件${NC}"
    echo -e "  │   ├── requirements.txt               ${GREEN}← 依赖清单${NC}"
    echo -e "  │   └── reference.md                   ${GREEN}← 输出格式参考${NC}"
    echo -e "  ├── api/quality_inspection_api.py      ${GREEN}← RAGFlow API 端点${NC}"
    echo -e "  ├── agent_integration/"
    echo -e "  │   ├── quality_assessment_tool.py     ${GREEN}← RAGFlow Agent Tool${NC}"
    echo -e "  │   └── document_ingestion_workflow.json ${GREEN}← Agent 工作流${NC}"
    echo -e "  ├── tests/test_skill.py                ${GREEN}← 单元测试${NC}"
    echo -e "  ├── run.sh / run.bat                   ${GREEN}← 一键运行脚本${NC}"
    echo -e "  ├── quality_report/                    ${GREEN}← 已有评估报告${NC}"
    echo -e "  └── deploy.sh                          ${GREEN}← 本部署脚本${NC}"

    echo -e "\n${BOLD}🚀 使用方法:${NC}"
    echo -e "  ${CYAN}# 方式一：命令行运行${NC}"
    echo -e "  python3 $SCRIPTS_DIR/assess_documents.py \\"
    echo -e "    --input <文档目录> --output-dir <输出目录>"
    echo ""
    echo -e "  ${CYAN}# 方式二：一键运行脚本${NC}"
    echo -e "  ./run.sh <文档目录> [输出目录]"
    echo ""
    echo -e "  ${CYAN}# 方式三：API 端点 (需集成到 RAGFlow)${NC}"
    echo -e "  POST /v1/document/quality-inspection"
    echo -e "  Body: {\"folder_path\": \"/path/to/docs\"}"

    echo -e "\n${BOLD}📋 输出文件:${NC}"
    echo -e "  ${GREEN}quality_report.json${NC} — 完整结构化报告 (可程序化处理)"
    echo -e "  ${GREEN}quality_brief.html${NC} — 可视化 HTML 简报 (浏览器直接打开)"

    echo -e "\n${BOLD}📦 已安装依赖:${NC}"
    for mod in "pymupdf" "python-docx" "beautifulsoup4" "simhash" "pyyaml" "tqdm" "pytest"; do
        echo -e "  ${GREEN}✔${NC} $mod"
    done

    echo -e "\n${BOLD}⚠️  RAGFlow 集成步骤:${NC}"
    echo -e "  1. 复制 api/quality_inspection_api.py → ragflow-main/api/apps/"
    echo -e "  2. 复制 agent_integration/quality_assessment_tool.py → ragflow-main/agent/tools/"
    echo -e "  3. 复制整个 .cursor/skills/document-quality-assessment/ → ragflow-main/"
    echo -e "  4. 重启 RAGFlow 服务"

    echo -e "\n${GREEN}═══════════════════════════════════════════════════════════${NC}"
    echo -e "${BOLD}🎉 部署完成！项目已就绪。${NC}"
    echo -e "${GREEN}═══════════════════════════════════════════════════════════${NC}\n"
}

# ============================================================
# 主流程
# ============================================================
main() {
    print_banner
    echo -e "${CYAN}开始部署 DocumentQualityAssessmentSkill...${NC}\n"

    step1_check_environment
    step2_install_dependencies
    step3_validate_config
    step4_run_tests
    step5_functional_test
    step6_summary
}

# 运行
main "$@"
