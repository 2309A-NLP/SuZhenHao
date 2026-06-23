#!/usr/bin/env python3
"""
工单16 - 评估脚本
对比基座模型 vs 微调模型在测试集上的准确率

用法：python evaluate.py
输出：评估报告 + 对比结果
"""

import json
import os
import re
import random
import torch
from pathlib import Path
from transformers import AutoProcessor, BitsAndBytesConfig, Qwen2VLForConditionalGeneration
from peft import PeftModel
from PIL import Image

# ========== 配置 ==========
BASE_MODEL_PATH = "/home/su/llamafactory_env/models/Qwen2-VL-2B-Instruct"
LORA_PATH = "/home/su/LlamaFactory-main/saves/Custom/lora/train_2026-06-13-08-15-30"
TEST_FILE = "/home/su/ragflow_vlm_data/dataset/test.jsonl"
OUTPUT_DIR = "/mnt/c/Users/23672/Desktop/2309A/实训一/工单16"

# 评估参数
MAX_SAMPLES = 300  # 从测试集中抽样 300 条进行评估（全量太慢）
RANDOM_SEED = 42
MAX_NEW_TOKENS = 50


def load_test_data(test_file, max_samples=300):
    """加载测试集并抽样"""
    samples = []
    with open(test_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))

    random.seed(RANDOM_SEED)
    if len(samples) > max_samples:
        samples = random.sample(samples, max_samples)

    return samples


def extract_answer(response):
    """从模型回复中提取答案字母"""
    # 尝试匹配 A/B/C/D
    response = response.strip()
    # 匹配开头的单个字母
    m = re.match(r'^([A-D])', response)
    if m:
        return m.group(1)
    # 匹配 "A." 或 "A、" 格式
    m = re.match(r'^([A-D])[.、]', response)
    if m:
        return m.group(1)
    return None


def load_model_and_processor(model_path, lora_path=None, quantize=True):
    """加载模型和处理器"""
    print(f"  加载模型: {model_path}")

    # 4-bit 量化配置
    bnb_config = None
    if quantize:
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
        )

    # 加载处理器
    processor = AutoProcessor.from_pretrained(model_path, trust_remote_code=True)

    # 加载模型
    model = Qwen2VLForConditionalGeneration.from_pretrained(
        model_path,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
        torch_dtype=torch.bfloat16,
    )

    # 加载 LoRA 适配器（如果提供）
    if lora_path and os.path.exists(lora_path):
        print(f"  加载 LoRA: {lora_path}")
        model = PeftModel.from_pretrained(model, lora_path)

    model.eval()
    return model, processor


def evaluate_model(model, processor, samples, model_name="model"):
    """评估模型在测试集上的表现"""
    correct = 0
    total = 0
    group_results = {"1": {"correct": 0, "total": 0},
                     "2": {"correct": 0, "total": 0},
                     "3": {"correct": 0, "total": 0}}
    errors = []

    for i, sample in enumerate(samples):
        if (i + 1) % 50 == 0:
            print(f"    [{model_name}] 进度: {i+1}/{len(samples)}, 当前准确率: {correct/total*100:.1f}%" if total > 0 else f"    [{model_name}] 进度: {i+1}/{len(samples)}")

        messages = sample["messages"]
        images = sample["images"]
        ground_truth = extract_answer(messages[1]["content"])
        group = str(sample.get("group", 0))

        if not ground_truth:
            continue

        # 构建输入
        user_content = messages[0]["content"]

        # 加载图片
        pil_images = []
        for img_path in images:
            if os.path.exists(img_path):
                pil_images.append(Image.open(img_path).convert("RGB"))

        if not pil_images:
            continue

        # 构建对话
        conversation = [
            {"role": "user", "content": [{"type": "image"}, {"type": "text", "text": user_content.replace("<image>", "")}]}
        ]

        try:
            # 处理输入
            text = processor.apply_chat_template(conversation, tokenize=False, add_generation_prompt=True)
            inputs = processor(text=text, images=pil_images, return_tensors="pt", padding=True)
            inputs = {k: v.to(model.device) for k, v in inputs.items()}

            # 生成回答
            with torch.no_grad():
                output_ids = model.generate(
                    **inputs,
                    max_new_tokens=MAX_NEW_TOKENS,
                    do_sample=False,
                    temperature=0.01,
                    top_k=1,
                    top_p=0.001,
                )

            # 解码输出
            generated_ids = output_ids[0][inputs["input_ids"].shape[1]:]
            response = processor.decode(generated_ids, skip_special_tokens=True).strip()

            # 提取答案
            predicted = extract_answer(response)

            total += 1
            if predicted == ground_truth:
                correct += 1
                if group in group_results:
                    group_results[group]["correct"] += 1
            else:
                errors.append({
                    "question": user_content[:100],
                    "predicted": predicted,
                    "ground_truth": ground_truth,
                    "group": group,
                    "response": response[:100],
                })

            if group in group_results:
                group_results[group]["total"] += 1

        except Exception as e:
            print(f"    ⚠️ 样本 {i} 出错: {e}")
            continue

    return {
        "model_name": model_name,
        "total": total,
        "correct": correct,
        "accuracy": correct / total * 100 if total > 0 else 0,
        "group_results": group_results,
        "errors": errors[:20],  # 保存前 20 个错误样本
    }


def main():
    print("=" * 60)
    print("工单16 - VLM 微调效果评估")
    print("=" * 60)

    # 1. 加载测试数据
    print(f"\n[1/5] 加载测试集...")
    samples = load_test_data(TEST_FILE, MAX_SAMPLES)
    print(f"  抽样 {len(samples)} 条进行评估")

    # 按 group 统计
    groups = {}
    for s in samples:
        g = str(s.get("group", 0))
        groups[g] = groups.get(g, 0) + 1
    print(f"  group 分布: {dict(sorted(groups.items()))}")

    # 2. 评估基座模型
    print(f"\n[2/5] 评估基座模型（微调前）...")
    base_model, processor = load_model_and_processor(BASE_MODEL_PATH, lora_path=None)
    base_results = evaluate_model(base_model, processor, samples, "基座模型")
    print(f"  基座模型准确率: {base_results['accuracy']:.1f}% ({base_results['correct']}/{base_results['total']})")

    # 释放显存
    del base_model
    torch.cuda.empty_cache()

    # 3. 评估微调模型
    print(f"\n[3/5] 评估微调模型（微调后）...")
    ft_model, processor = load_model_and_processor(BASE_MODEL_PATH, lora_path=LORA_PATH)
    ft_results = evaluate_model(ft_model, processor, samples, "微调模型")
    print(f"  微调模型准确率: {ft_results['accuracy']:.1f}% ({ft_results['correct']}/{ft_results['total']})")

    # 释放显存
    del ft_model
    torch.cuda.empty_cache()

    # 4. 对比分析
    print(f"\n[4/5] 对比分析...")
    improvement = ft_results["accuracy"] - base_results["accuracy"]

    print(f"\n{'='*60}")
    print(f"评估结果对比")
    print(f"{'='*60}")
    print(f"{'指标':<20} {'基座模型':>10} {'微调模型':>10} {'提升':>10}")
    print(f"{'-'*50}")
    print(f"{'总准确率':<18} {base_results['accuracy']:>9.1f}% {ft_results['accuracy']:>9.1f}% {improvement:>+9.1f}%")

    for g in ["1", "2", "3"]:
        group_name = {"1": "文本理解", "2": "图纸位置", "3": "图纸推理"}[g]
        base_g = base_results["group_results"][g]
        ft_g = ft_results["group_results"][g]
        base_acc = base_g["correct"] / base_g["total"] * 100 if base_g["total"] > 0 else 0
        ft_acc = ft_g["correct"] / ft_g["total"] * 100 if ft_g["total"] > 0 else 0
        print(f"  group {g} ({group_name})  {base_acc:>8.1f}% {ft_acc:>8.1f}% {ft_acc-base_acc:>+8.1f}%")

    print(f"{'='*60}")

    # 5. 保存报告
    print(f"\n[5/5] 保存评估报告...")
    report = {
        "test_samples": len(samples),
        "base_model": base_results,
        "fine_tuned_model": ft_results,
        "improvement": improvement,
    }

    report_file = os.path.join(OUTPUT_DIR, "evaluation_report.json")
    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  ✅ {report_file}")

    # 保存错误样本
    errors_file = os.path.join(OUTPUT_DIR, "error_analysis.json")
    with open(errors_file, "w", encoding="utf-8") as f:
        json.dump({
            "base_errors": base_results["errors"][:10],
            "ft_errors": ft_results["errors"][:10],
        }, f, ensure_ascii=False, indent=2)
    print(f"  ✅ {errors_file}")

    print(f"\n{'='*60}")
    print(f"评估完成！")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
