#!/usr/bin/env python3
"""
工单16 - 构建VLM微调数据集
将 questions.jsonl + 提取的图片 → LLaMA-Factory 格式的 JSONL 数据集

用法：python build_dataset.py
输入：questions.jsonl + /home/su/ragflow_vlm_data/images/
输出：/home/su/ragflow_vlm_data/dataset/{train,val,test}.jsonl
      /home/su/ragflow_vlm_data/dataset/dataset_info.json
"""

import json
import os
import random
import re
from pathlib import Path

# ========== 配置 ==========
QUESTIONS_FILE = "/mnt/c/Users/23672/Desktop/RAG 新工单/14-17附件/original_problems/questions.jsonl"
IMAGE_DIR = "/home/su/ragflow_vlm_data/images"
OUTPUT_DIR = "/home/su/ragflow_vlm_data/dataset"

# 数据集划分比例
TRAIN_RATIO = 0.8
VAL_RATIO = 0.1
TEST_RATIO = 0.1
RANDOM_SEED = 42

# LLaMA-Factory 的 images 路径需要相对于数据集目录或使用绝对路径
# 这里使用绝对路径，因为 LLaMA-Factory 在 WSL 中运行
USE_ABSOLUTE_PATH = True


def load_questions(questions_file):
    """加载 questions.jsonl"""
    data = []
    with open(questions_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data.append(json.loads(line))
    return data


def find_image_path(item, image_dir):
    """根据题目找到对应的图片路径"""
    doc_name = Path(item["document"]).stem
    question = item["question"]
    
    # 提取页码
    m = re.search(r"第(\d+)页", question)
    if m:
        page_num = int(m.group(1))
    else:
        # group 1 纯文本题，使用第1页
        page_num = 1
    
    img_path = os.path.join(image_dir, doc_name, f"page_{page_num:02d}.png")
    
    if os.path.exists(img_path):
        return img_path
    return None


def format_options(options):
    """格式化选项为可读文本"""
    return "\n".join(options)


def build_sample(item, image_path):
    """构建一条微调样本"""
    question = item["question"]
    options = format_options(item["options"])
    answer = item["answer"]
    group = item["group"]
    
    # 构建 user prompt
    # 使用 <image> 标记告诉模型看图
    user_content = f"<image>{question}\n\n选项：\n{options}"
    
    # 构建 assistant response
    # 给出选项字母 + 完整答案文本
    answer_text = ""
    for opt in item["options"]:
        if opt.startswith(answer + ".") or opt.startswith(answer + "、"):
            answer_text = opt
            break
    
    assistant_content = f"{answer}\n{answer_text}" if answer_text else answer
    
    # LLaMA-Factory messages 格式
    sample = {
        "messages": [
            {"content": user_content, "role": "user"},
            {"content": assistant_content, "role": "assistant"}
        ],
        "images": [image_path]
    }
    
    return sample


def main():
    print("=" * 60)
    print("工单16 - 构建VLM微调数据集")
    print("=" * 60)
    
    # 1. 加载题目
    print("\n[1/4] 加载 questions.jsonl...")
    questions = load_questions(QUESTIONS_FILE)
    print(f"  共 {len(questions)} 条题目")
    
    # 2. 匹配图片
    print(f"\n[2/4] 匹配图片...")
    samples = []
    no_image = 0
    
    for item in questions:
        img_path = find_image_path(item, IMAGE_DIR)
        if img_path:
            sample = build_sample(item, img_path)
            samples.append(sample)
        else:
            no_image += 1
    
    print(f"  成功匹配: {len(samples)} 条")
    print(f"  无图片跳过: {no_image} 条")
    
    # 3. 划分数据集
    print(f"\n[3/4] 划分数据集 (train={TRAIN_RATIO}, val={VAL_RATIO}, test={TEST_RATIO})...")
    random.seed(RANDOM_SEED)
    random.shuffle(samples)
    
    n = len(samples)
    n_train = int(n * TRAIN_RATIO)
    n_val = int(n * VAL_RATIO)
    
    train_data = samples[:n_train]
    val_data = samples[n_train:n_train + n_val]
    test_data = samples[n_train + n_val:]
    
    print(f"  训练集: {len(train_data)} 条")
    print(f"  验证集: {len(val_data)} 条")
    print(f"  测试集: {len(test_data)} 条")
    
    # 4. 保存
    print(f"\n[4/4] 保存数据集...")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for name, data in [("train", train_data), ("val", val_data), ("test", test_data)]:
        output_file = os.path.join(OUTPUT_DIR, f"{name}.jsonl")
        with open(output_file, "w", encoding="utf-8") as f:
            for sample in data:
                f.write(json.dumps(sample, ensure_ascii=False) + "\n")
        print(f"  ✅ {output_file}")
    
    # 生成 dataset_info.json（LLaMA-Factory 注册数据集用）
    dataset_info = {
        "vlm_industrial_qa_train": {
            "file_name": "train.jsonl",
            "formatting": "sharegpt",
            "columns": {
                "messages": "messages",
                "images": "images"
            },
            "tags": {
                "role_tag": "role",
                "content_tag": "content",
                "user_tag": "user",
                "assistant_tag": "assistant"
            }
        },
        "vlm_industrial_qa_val": {
            "file_name": "val.jsonl",
            "formatting": "sharegpt",
            "columns": {
                "messages": "messages",
                "images": "images"
            },
            "tags": {
                "role_tag": "role",
                "content_tag": "content",
                "user_tag": "user",
                "assistant_tag": "assistant"
            }
        },
        "vlm_industrial_qa_test": {
            "file_name": "test.jsonl",
            "formatting": "sharegpt",
            "columns": {
                "messages": "messages",
                "images": "images"
            },
            "tags": {
                "role_tag": "role",
                "content_tag": "content",
                "user_tag": "user",
                "assistant_tag": "assistant"
            }
        }
    }
    
    info_file = os.path.join(OUTPUT_DIR, "dataset_info.json")
    with open(info_file, "w", encoding="utf-8") as f:
        json.dump(dataset_info, f, ensure_ascii=False, indent=2)
    print(f"  ✅ {info_file}")
    
    # 统计信息
    print(f"\n{'=' * 60}")
    print(f"数据集构建完成！")
    print(f"{'=' * 60}")
    print(f"\n统计：")
    print(f"  总样本数: {len(samples)}")
    
    # 按 group 统计
    groups = {"1": 0, "2": 0, "3": 0}
    for item in questions:
        g = str(item["group"])
        if g in groups:
            groups[g] += 1
    print(f"  group 1 (文本理解): {groups['1']}")
    print(f"  group 2 (图纸位置): {groups['2']}")
    print(f"  group 3 (图纸推理): {groups['3']}")
    print(f"\n文件位置: {OUTPUT_DIR}")
    print(f"  dataset_info.json  → LLaMA-Factory 注册数据集")
    print(f"  train.jsonl         → 训练集")
    print(f"  val.jsonl           → 验证集")
    print(f"  test.jsonl          → 测试集（评估用）")


if __name__ == "__main__":
    main()
