#!/bin/bash
# 工单16 - 命令行启动 QLoRA 微调（简化版）
echo "启动 QLoRA 微调..."
source /home/su/llamafactory_env/bin/activate
llamafactory-cli train /mnt/c/Users/23672/Desktop/2309A/实训一/工单16/qlora_config_v2.yaml
