#!/bin/bash
# ============================================================
# 文档质量评估工具 — 一键运行脚本 (Linux/Mac/WSL)
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SKILL_DIR="$SCRIPT_DIR/.cursor/skills/document-quality-assessment"

echo "========================================"
echo " DocumentQualityAssessmentSkill"
echo " 文档质量评估工具"
echo "========================================"
echo

# 检查参数
if [ -z "$1" ]; then
    echo "用法: ./run.sh <文档目录> [输出目录]"
    echo "示例: ./run.sh /path/to/documents /path/to/output"
    exit 1
fi

INPUT_DIR="$1"
OUTPUT_DIR="${2:-$SCRIPT_DIR/quality_report}"

# 安装依赖
echo "[1/3] 检查依赖..."
pip install -r "$SKILL_DIR/requirements.txt" -q 2>/dev/null

# 运行评估
echo "[2/3] 执行质量评估..."
python3 "$SKILL_DIR/scripts/assess_documents.py" --input "$INPUT_DIR" --output-dir "$OUTPUT_DIR"

# 完成
echo
echo "[3/3] 完成！"
echo "JSON报告: $OUTPUT_DIR/quality_report.json"
echo "HTML简报: $OUTPUT_DIR/quality_brief.html"
echo
echo "在浏览器中打开 HTML 简报查看可视化结果。"
