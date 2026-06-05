# -*- coding: utf-8 -*-
# !/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试微调模型效果
对比原始模型和微调模型的检索性能
"""

import os
import json
import numpy as np
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity

# 配置
ORIGINAL_MODEL_PATH = r"C:\Users\23672\Desktop\模型\m3e-base"
FINETUNED_MODEL_PATH = "./finetuned_model"
EVAL_DATA_FILE = "./finetune_data/eval.jsonl"

# 如果评估集不存在，使用内置测试用例
FALLBACK_QUERIES = [
    ("公司2023年的营业收入是多少？", "营业收入.*?19,813.64"),
    ("公司的实际控制人是谁？", "程家明"),
    ("公司面临的主要风险有哪些？", "风险"),
    ("公司的核心技术是什么？", "视音频中间件"),
]


def load_eval_data(file_path):
    """加载评估数据"""
    if not os.path.exists(file_path):
        print(f"⚠️ 评估文件不存在: {file_path}")
        print("使用内置测试用例...")
        return None

    pairs = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            data = json.loads(line.strip())
            pairs.append((data["query"], data["positive"]))
    print(f"✓ 从 {file_path} 加载了 {len(pairs)} 个测试用例")
    return pairs


def evaluate_model(model_path, test_pairs, model_name):
    """评估模型在测试用例上的表现"""
    print(f"\n{'=' * 50}")
    print(f"评估模型: {model_name}")
    print(f"{'=' * 50}")

    model = SentenceTransformer(model_path)

    queries = [q for q, _ in test_pairs]
    positives = [p for _, p in test_pairs]

    # 编码
    q_embs = model.encode(queries, convert_to_numpy=True)
    p_embs = model.encode(positives, convert_to_numpy=True)

    # 计算相似度矩阵
    sim_matrix = cosine_similarity(q_embs, p_embs)

    # 计算 Recall@K
    recall_at_k = {}
    for k in [1, 3, 5]:
        correct = 0
        for i in range(len(queries)):
            # 获取第 i 个查询对所有文档的相似度
            scores = sim_matrix[i]
            top_k_indices = np.argsort(scores)[-k:][::-1]
            if i in top_k_indices:
                correct += 1
        recall_at_k[f"Recall@{k}"] = correct / len(queries)

    # 平均相似度（正确答案）
    avg_sim = np.mean([sim_matrix[i, i] for i in range(len(queries))])

    # 输出结果
    for k, v in recall_at_k.items():
        print(f"  {k}: {v:.4f} ({v * 100:.2f}%)")
    print(f"  avg_similarity: {avg_sim:.4f}")

    return recall_at_k, avg_sim


def compare_models(original_path, finetuned_path, test_pairs):
    """对比两个模型"""
    print("\n" + "=" * 60)
    print("📊 微调效果对比")
    print("=" * 60)

    orig_result, orig_sim = evaluate_model(original_path, test_pairs, "原始模型 (m3e-base)")
    fine_result, fine_sim = evaluate_model(finetuned_path, test_pairs, "微调模型")

    print("\n" + "-" * 50)
    print("📈 性能对比")
    print("-" * 50)
    for k in ["Recall@1", "Recall@3", "Recall@5"]:
        orig = orig_result.get(k, 0)
        fine = fine_result.get(k, 0)
        diff = fine - orig
        arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
        print(f"  {k}: {orig:.4f} → {fine:.4f} ({arrow} {abs(diff):.4f})")
    diff_sim = fine_sim - orig_sim
    arrow_sim = "↑" if diff_sim > 0 else "↓"
    print(f"  avg_similarity: {orig_sim:.4f} → {fine_sim:.4f} ({arrow_sim} {abs(diff_sim):.4f})")


def interactive_test(finetuned_path):
    """交互式测试：用户输入查询，对比两个模型的检索结果"""
    print("\n" + "=" * 60)
    print("🎤 交互式测试 (输入 'exit' 退出)")
    print("=" * 60)

    orig_model = SentenceTransformer(ORIGINAL_MODEL_PATH)
    fine_model = SentenceTransformer(finetuned_path)

    # 使用已有的 chunks 作为检索库（如果有）
    try:
        import pickle
        from pathlib import Path
        chunks_path = Path("./data/faiss_index/chunks.pkl")
        if chunks_path.exists():
            with open(chunks_path, "rb") as f:
                chunks = pickle.load(f)
            doc_texts = [c.get("content", "") for c in chunks]
            print(f"✓ 加载了 {len(doc_texts)} 个文档块作为检索库")
        else:
            doc_texts = []
            print("⚠️ 未找到索引文件，将只能对比相似度，无法展示检索结果")
    except Exception as e:
        doc_texts = []
        print(f"⚠️ 加载文档库失败: {e}")

    while True:
        query = input("\n请输入问题: ").strip()
        if query.lower() in ("exit", "quit", "q"):
            break
        if not query:
            continue

        # 编码
        q_emb_orig = orig_model.encode([query])[0]
        q_emb_fine = fine_model.encode([query])[0]

        if doc_texts:
            # 计算与所有文档的相似度
            doc_embs_orig = orig_model.encode(doc_texts)
            doc_embs_fine = fine_model.encode(doc_texts)
            sims_orig = cosine_similarity([q_emb_orig], doc_embs_orig)[0]
            sims_fine = cosine_similarity([q_emb_fine], doc_embs_fine)[0]

            top3_orig = np.argsort(sims_orig)[-3:][::-1]
            top3_fine = np.argsort(sims_fine)[-3:][::-1]

            print("\n【原始模型】Top3 相关文档片段:")
            for i, idx in enumerate(top3_orig):
                print(f"  {i + 1}. (相似度 {sims_orig[idx]:.3f}) {doc_texts[idx][:100]}...")

            print("\n【微调模型】Top3 相关文档片段:")
            for i, idx in enumerate(top3_fine):
                print(f"  {i + 1}. (相似度 {sims_fine[idx]:.3f}) {doc_texts[idx][:100]}...")
        else:
            # 仅输出向量对比（无文档库）
            print(f"\n原始模型查询向量前5维: {q_emb_orig[:5]}")
            print(f"微调模型查询向量前5维: {q_emb_fine[:5]}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="测试微调模型效果")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互式测试（输入查询对比检索结果）")
    parser.add_argument("--quick", "-q", action="store_true", help="快速测试（仅输出评估指标）")
    args = parser.parse_args()

    # 加载测试数据
    test_pairs = load_eval_data(EVAL_DATA_FILE)
    if not test_pairs:
        # 使用内置测试用例
        test_pairs = []
        for q, p in FALLBACK_QUERIES:
            test_pairs.append((q, p))
        print(f"使用 {len(test_pairs)} 个内置测试用例")

    if not test_pairs:
        print("❌ 没有可用的测试用例")
        return

    if args.interactive:
        interactive_test(FINETUNED_MODEL_PATH)
    elif args.quick:
        # 仅输出评估指标
        evaluate_model(FINETUNED_MODEL_PATH, test_pairs, "微调模型")
    else:
        # 默认对比模式
        compare_models(ORIGINAL_MODEL_PATH, FINETUNED_MODEL_PATH, test_pairs)


if __name__ == "__main__":
    main()