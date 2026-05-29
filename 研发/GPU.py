# -*- coding: utf-8 -*-
import torch

if torch.cuda.is_available():
    # 获取当前默认 GPU 的型号（索引 0 通常为第一块 GPU）
    gpu_name = torch.cuda.get_device_name(0)
    print(f"GPU 型号：{gpu_name}")
else:
    print("CUDA 不可用，未检测到 GPU。")