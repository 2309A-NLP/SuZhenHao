#!/bin/bash
# 工单16 - 启动 LLaMA-Factory WebUI
# 用法: bash launch_webui.sh

echo "=========================================="
echo "  启动 LLaMA-Factory WebUI (LlamaBoard)"
echo "=========================================="

# 激活虚拟环境
source /home/su/llamafactory_env/bin/activate

# 启动 WebUI
# --host 0.0.0.0 允许外部访问（WSL中需要）
# --share 创建公网链接（可选）
llamafactory-cli webui --host 0.0.0.0 --port 7860
