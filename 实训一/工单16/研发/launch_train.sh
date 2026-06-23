#!/bin/bash
# 工单16 - 使用配置文件启动 QLoRA 微调（命令行方式）
# 用法: bash launch_train.sh

echo "=========================================="
echo "  工单16 - QLoRA 微调 Qwen2-VL-2B-Instruct"
echo "=========================================="

# 激活虚拟环境
source /home/su/llamafactory_env/bin/activate

# 使用配置文件启动训练
llamafactory-cli train /mnt/c/Users/23672/Desktop/2309A/实训一/工单16/qlora_config.yaml
