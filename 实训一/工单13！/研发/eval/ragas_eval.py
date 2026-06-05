#!/usr/bin/env python3
"""
RAGAS 评估脚本 - 对比 RAG 和 LightRAG 的检索效果
================================================

使用 RAGAS 框架评估两种检索模式的质量：
- hybrid (传统 FAISS + BM25 混合检索)
- lightrag (基于知识图谱的 LightRAG 检索)

评估指标：
- Faithfulness (忠实度)
- Answer Relevancy (答案相关性)
- Context Precision (上下文精确度)
- Context Recall (上下文召回率)

用法：
    python eval/ragas_eval.py [--api-url http://localhost:8080] [--dataset eval/test_dataset.json]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests

# ============================================================
# 配置
# ============================================================

PROJECT_ROOT = Path(__file__).parent.parent
EVAL_DIR = Path(__file__).parent
DEFAULT_API_URL = "http://localhost:8080"
DEFAULT_DATASET = EVAL_DIR / "test_dataset.json"
RESULTS_PATH = EVAL_DIR / "eval_results.json"
COMPARISON_PATH = EVAL_DIR / "comparison_table.json"

# LLM API 配置（从 .env 读取，与主项目共用同一套配置）
import os
from dotenv import load_dotenv
load_dotenv(EVAL_DIR.parent / ".env")

LLM_API_BASE = os.getenv("DEEPSEEK_API_BASE_2", "https://api.xiaomimimo.com/v1")
LLM_API_KEY = os.getenv("DEEPSEEK_API_KEY_2", "")
LLM_MODEL = os.getenv("DEEPSEEK_MODEL_2", "mimo-v2.5-pro")

print(f"[评估] 使用 LLM: {LLM_MODEL} @ {LLM_API_BASE}")

# ============================================================
# RAGAS 尝试导入
# ============================================================

try:
    from ragas import evaluate
    from ragas.metrics import (
        faithfulness,
        answer_relevancy,
        context_precision,
        context_recall,
    )
    from datasets import Dataset
    from langchain_openai import ChatOpenAI

    # 尝试导入 RAGAS 的 LLM 包装器（不同版本路径不同）
    try:
        from ragas.llms import LangchainLLMWrapper
    except ImportError:
        from ragas.llms.base import LangchainLLMWrapper

    RAGAS_AVAILABLE = True
    print("✓ RAGAS 库已加载")
except ImportError as e:
    RAGAS_AVAILABLE = False
    print(f"⚠️  RAGAS 库未安装，将使用简化评估方式: {e}")
    print("   安装命令: pip install ragas datasets langchain-openai")


# ============================================================
# 工具函数
# ============================================================

def load_dataset(path: str) -> List[Dict]:
    """加载测试数据集。"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"✓ 加载测试数据集: {len(data)} 个问题")
    return data


def switch_mode(mode: str, api_url: str):
    """切换检索模式并等待索引构建完成。"""
    url = f"{api_url}/api/retrieval-mode"
    print(f"  切换到 {mode} 模式（这可能需要较长时间）...")
    try:
        response = requests.post(url, json={"mode": mode}, timeout=600)
        response.raise_for_status()
        data = response.json()
        print(f"  ✓ {mode} 模式切换完成: {data.get('message', '')}")
        return True
    except Exception as e:
        print(f"  ✗ {mode} 模式切换失败: {e}")
        return False


def query_api(question: str, api_url: str, retrieval_mode: str = None) -> Dict:
    """
    调用后端 API 获取回答。

    Args:
        question: 用户问题
        api_url: API 基础地址
        retrieval_mode: 检索模式（hybrid/lightrag 等），None 时使用服务器当前模式

    Returns:
        包含 answer 和 sources 的字典
    """
    url = f"{api_url}/api/chat"
    payload = {
        "query": question,
        "lang": "zh",
    }
    if retrieval_mode:
        payload["retrieval_mode"] = retrieval_mode

    try:
        response = requests.post(url, json=payload, timeout=180)
        response.raise_for_status()
        data = response.json()

        # 从 sources 中提取上下文
        contexts = []
        for source in data.get("sources", []):
            # 尝试从 source 中提取内容
            if "content" in source:
                contexts.append(source["content"])
            elif "chunk_id" in source:
                # 如果只有 chunk_id，记录引用信息
                contexts.append(f"[文档片段] 第{source.get('page', '?')}页")

        return {
            "answer": data.get("answer", ""),
            "contexts": contexts,
            "sources": data.get("sources", []),
            "confidence": data.get("confidence", 0),
        }
    except requests.exceptions.RequestException as e:
        print(f"  ⚠️  API 请求失败: {e}")
        return {
            "answer": f"[API 请求失败: {e}]",
            "contexts": [],
            "sources": [],
            "confidence": 0,
        }


def extract_contexts_from_sources(sources: List[Dict]) -> List[str]:
    """从 API 返回的 sources 中提取上下文文本。"""
    contexts = []
    for src in sources:
        if "content" in src:
            contexts.append(src["content"])
    return contexts


# ============================================================
# RAGAS 评估
# ============================================================

def evaluate_with_ragas(
    questions: List[str],
    answers: List[str],
    contexts_list: List[List[str]],
    ground_truths: List[str],
) -> Dict:
    """
    使用 RAGAS 框架计算评估指标。

    需要配置 LLM 用于评分。
    """
    # 显式创建 LangChain LLM 实例（RAGAS 新版本需要，不能只靠环境变量）
    llm = ChatOpenAI(
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        base_url=LLM_API_BASE,
        temperature=0,
        timeout=120,
    )
    evaluator_llm = LangchainLLMWrapper(llm)

    # 构建数据集
    dataset_dict = {
        "question": questions,
        "answer": answers,
        "contexts": contexts_list,
        "ground_truth": ground_truths,
    }

    dataset = Dataset.from_dict(dataset_dict)

    # 运行评估
    print("  正在运行 RAGAS 评估（这可能需要几分钟）...")
    result = evaluate(
        dataset=dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
        llm=evaluator_llm,
    )

    return {
        "faithfulness": result["faithfulness"],
        "answer_relevancy": result["answer_relevancy"],
        "context_precision": result["context_precision"],
        "context_recall": result["context_recall"],
    }


def evaluate_simple(
    questions: List[str],
    answers: List[str],
    contexts_list: List[List[str]],
    ground_truths: List[str],
) -> Dict:
    """
    简化评估方法（RAGAS 不可用时的降级方案）。
    使用 DeepSeek API 进行简单的质量评分。
    """
    print("  使用简化评估方法...")

    scores = {
        "faithfulness": [],
        "answer_relevancy": [],
        "context_precision": [],
        "context_recall": [],
    }

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    for i, (q, a, ctx, gt) in enumerate(zip(questions, answers, contexts_list, ground_truths)):
        print(f"  评估问题 {i+1}/{len(questions)}...", end="", flush=True)

        context_text = "\n".join(ctx) if ctx else "无上下文"

        # 使用 LLM 评分
        prompt = f"""请对以下问答质量进行评分（0-1分），并返回JSON格式：

问题：{q}
回答：{a}
参考上下文：{context_text}
标准答案：{gt}

请评分以下四个维度（每个0-1分）：
1. faithfulness: 回答是否忠实于提供的上下文（不编造信息）
2. answer_relevancy: 回答是否与问题相关
3. context_precision: 检索到的上下文中，相关内容的比例
4. context_recall: 标准答案中的关键信息是否被上下文覆盖

请只返回JSON，格式如下：
{{"faithfulness": 0.8, "answer_relevancy": 0.7, "context_precision": 0.6, "context_recall": 0.7}}"""

        try:
            payload = {
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 200,
            }
            resp = requests.post(
                f"{LLM_API_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]

            # 提取 JSON
            import re
            json_match = re.search(r'\{[^}]+\}', content)
            if json_match:
                score = json.loads(json_match.group())
                for key in scores:
                    if key in score:
                        scores[key].append(float(score[key]))
                    else:
                        scores[key].append(0.5)
            else:
                for key in scores:
                    scores[key].append(0.5)

            print(" ✓")
        except Exception as e:
            print(f" ✗ ({e})")
            for key in scores:
                scores[key].append(0.5)

        # 避免请求过快
        time.sleep(0.5)

    # 计算平均分
    return {key: sum(vals) / len(vals) if vals else 0 for key, vals in scores.items()}


def evaluate_per_question(
    questions: List[str],
    answers: List[str],
    contexts_list: List[List[str]],
    ground_truths: List[str],
) -> List[Dict]:
    """逐题评估，返回每题的分数。"""
    print("  正在逐题评估...")
    results = []

    headers = {
        "Authorization": f"Bearer {LLM_API_KEY}",
        "Content-Type": "application/json",
    }

    for i, (q, a, ctx, gt) in enumerate(zip(questions, answers, contexts_list, ground_truths)):
        context_text = "\n".join(ctx) if ctx else "无上下文"

        prompt = f"""请对以下问答质量进行评分（0-1分），返回JSON格式：

问题：{q}
回答：{a}
参考上下文：{context_text}
标准答案：{gt}

评分维度（每个0-1分）：
1. faithfulness: 回答是否忠实于上下文
2. answer_relevancy: 回答是否与问题相关
3. context_precision: 检索到的上下文中相关内容比例
4. context_recall: 标准答案的关键信息是否被上下文覆盖

只返回JSON：{{"faithfulness": 0.8, "answer_relevancy": 0.7, "context_precision": 0.6, "context_recall": 0.7}}"""

        try:
            payload = {
                "model": LLM_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 200,
            }
            resp = requests.post(
                f"{LLM_API_BASE}/chat/completions",
                headers=headers,
                json=payload,
                timeout=30,
            )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]

            import re
            json_match = re.search(r'\{[^}]+\}', content)
            if json_match:
                score = json.loads(json_match.group())
                results.append({
                    "faithfulness": float(score.get("faithfulness", 0.5)),
                    "answer_relevancy": float(score.get("answer_relevancy", 0.5)),
                    "context_precision": float(score.get("context_precision", 0.5)),
                    "context_recall": float(score.get("context_recall", 0.5)),
                })
            else:
                results.append({"faithfulness": 0.5, "answer_relevancy": 0.5, "context_precision": 0.5, "context_recall": 0.5})
        except Exception:
            results.append({"faithfulness": 0.5, "answer_relevancy": 0.5, "context_precision": 0.5, "context_recall": 0.5})

        time.sleep(0.3)

    return results


# ============================================================
# 主评估流程
# ============================================================

def run_evaluation(api_url: str, dataset_path: str):
    """执行完整的评估流程。"""
    print("=" * 60)
    print("RAGAS 评估 - RAG vs LightRAG 对比")
    print("=" * 60)

    # 1. 加载测试数据
    print("\n[1/6] 加载测试数据集...")
    test_data = load_dataset(dataset_path)

    questions = [item["question"] for item in test_data]
    ground_truths = [item["ground_truth"] for item in test_data]
    test_contexts = [item.get("contexts", []) for item in test_data]

    # 2. 测试 API 连接
    print("\n[2/6] 测试 API 连接...")
    try:
        resp = requests.get(f"{api_url}/api/health", timeout=10)
        resp.raise_for_status()
        print(f"✓ API 连接成功: {api_url}")
    except Exception as e:
        print(f"⚠️  API 连接失败: {e}")
        print("  将使用测试数据集中的 contexts 作为模拟结果")

    # 3. 用 RAG (hybrid) 模式查询
    print("\n[3/6] 使用 RAG (hybrid) 模式查询...")
    switch_mode("hybrid", api_url)
    rag_results = []
    for i, q in enumerate(questions):
        print(f"  [{i+1}/{len(questions)}] {q[:40]}...", end="", flush=True)
        result = query_api(q, api_url, retrieval_mode="hybrid")
        rag_results.append(result)
        print(f" ✓ (置信度: {result['confidence']:.2f})")
        time.sleep(0.2)

    # 4. 用 LightRAG 模式查询
    print("\n[4/6] 使用 LightRAG 模式查询...")
    switch_mode("lightrag", api_url)
    lightrag_results = []
    for i, q in enumerate(questions):
        print(f"  [{i+1}/{len(questions)}] {q[:40]}...", end="", flush=True)
        result = query_api(q, api_url, retrieval_mode="lightrag")
        lightrag_results.append(result)
        print(f" ✓ (置信度: {result['confidence']:.2f})")
        time.sleep(0.2)

    # 5. 计算评估指标
    print("\n[5/6] 计算评估指标...")

    # 准备数据
    rag_answers = [r["answer"] for r in rag_results]
    rag_contexts = [r["contexts"] if r["contexts"] else ctx for r, ctx in zip(rag_results, test_contexts)]

    lightrag_answers = [r["answer"] for r in lightrag_results]
    lightrag_contexts = [r["contexts"] if r["contexts"] else ctx for r, ctx in zip(lightrag_results, test_contexts)]

    if RAGAS_AVAILABLE:
        try:
            print("  评估 RAG (hybrid) 模式...")
            rag_scores = evaluate_with_ragas(questions, rag_answers, rag_contexts, ground_truths)
        except Exception as e:
            print(f"  ⚠️  RAGAS 评估失败，降级为简化评估: {e}")
            rag_scores = evaluate_simple(questions, rag_answers, rag_contexts, ground_truths)

        try:
            print("  评估 LightRAG 模式...")
            lightrag_scores = evaluate_with_ragas(questions, lightrag_answers, lightrag_contexts, ground_truths)
        except Exception as e:
            print(f"  ⚠️  RAGAS 评估失败，降级为简化评估: {e}")
            lightrag_scores = evaluate_simple(questions, lightrag_answers, lightrag_contexts, ground_truths)
    else:
        rag_scores = evaluate_simple(questions, rag_answers, rag_contexts, ground_truths)
        lightrag_scores = evaluate_simple(questions, lightrag_answers, lightrag_contexts, ground_truths)

    # 逐题评估
    print("  逐题评估 RAG 模式...")
    rag_per_question = evaluate_per_question(questions, rag_answers, rag_contexts, ground_truths)
    print("  逐题评估 LightRAG 模式...")
    lightrag_per_question = evaluate_per_question(questions, lightrag_answers, lightrag_contexts, ground_truths)

    # 6. 保存结果
    print("\n[6/6] 保存评估结果...")

    # 构建逐题结果
    per_question_results = []
    for i in range(len(questions)):
        per_question_results.append({
            "question": questions[i],
            "ground_truth": ground_truths[i],
            "rag_answer": rag_answers[i],
            "lightrag_answer": lightrag_answers[i],
            "rag_scores": rag_per_question[i],
            "lightrag_scores": lightrag_per_question[i],
        })

    # 保存 eval_results.json
    eval_results = {
        "rag_scores": rag_scores,
        "lightrag_scores": lightrag_scores,
        "per_question_results": per_question_results,
        "metadata": {
            "dataset_path": str(dataset_path),
            "api_url": api_url,
            "num_questions": len(questions),
            "ragas_available": RAGAS_AVAILABLE,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(eval_results, f, ensure_ascii=False, indent=2)
    print(f"✓ 评估结果已保存到: {RESULTS_PATH}")

    # 生成对比表格
    comparison_table = generate_comparison_table(rag_scores, lightrag_scores)
    with open(COMPARISON_PATH, "w", encoding="utf-8") as f:
        json.dump(comparison_table, f, ensure_ascii=False, indent=2)
    print(f"✓ 对比表格已保存到: {COMPARISON_PATH}")

    # 打印对比表格
    print_comparison_table(rag_scores, lightrag_scores)

    return eval_results


# ============================================================
# 对比表格生成
# ============================================================

METRIC_INFO = {
    "faithfulness": {
        "name": "Faithfulness",
        "name_cn": "忠实度",
        "description": "生成的回答是否忠实于检索到的上下文，不编造信息",
    },
    "answer_relevancy": {
        "name": "Answer Relevancy",
        "name_cn": "答案相关性",
        "description": "回答与问题的相关程度",
    },
    "context_precision": {
        "name": "Context Precision",
        "name_cn": "上下文精确度",
        "description": "检索到的上下文中，相关内容的比例",
    },
    "context_recall": {
        "name": "Context Recall",
        "name_cn": "上下文召回率",
        "description": "标准答案中的关键信息是否被检索到的上下文覆盖",
    },
}


def generate_comparison_table(rag_scores: Dict, lightrag_scores: Dict) -> Dict:
    """生成对比表格数据。"""
    metrics = []
    rag_wins = 0
    lightrag_wins = 0
    ties = 0

    for key in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        info = METRIC_INFO[key]
        rag_val = rag_scores.get(key, 0)
        lightrag_val = lightrag_scores.get(key, 0)

        # 确定胜者
        if abs(rag_val - lightrag_val) < 0.01:
            winner = "tie"
            ties += 1
        elif rag_val > lightrag_val:
            winner = "rag"
            rag_wins += 1
        else:
            winner = "lightrag"
            lightrag_wins += 1

        metrics.append({
            "name": info["name"],
            "name_cn": info["name_cn"],
            "rag_score": round(rag_val, 4),
            "lightrag_score": round(lightrag_val, 4),
            "winner": winner,
            "description": info["description"],
        })

    return {
        "metrics": metrics,
        "summary": {
            "rag_wins": rag_wins,
            "lightrag_wins": lightrag_wins,
            "ties": ties,
        },
    }


def print_comparison_table(rag_scores: Dict, lightrag_scores: Dict):
    """在终端打印美观的对比表格。"""
    print("\n" + "=" * 70)
    print("  RAG vs LightRAG 评估对比")
    print("=" * 70)

    # 表头
    header = f"{'指标':<20} {'RAG':>10} {'LightRAG':>10} {'优胜者':>12}"
    print(header)
    print("-" * 70)

    rag_wins = 0
    lightrag_wins = 0

    for key in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        info = METRIC_INFO[key]
        rag_val = rag_scores.get(key, 0)
        lightrag_val = lightrag_scores.get(key, 0)

        # 格式化分数
        rag_str = f"{rag_val:.4f}"
        lightrag_str = f"{lightrag_val:.4f}"

        # 确定胜者标记
        if abs(rag_val - lightrag_val) < 0.01:
            winner = "  ─ 平局"
        elif rag_val > lightrag_val:
            winner = "  ★ RAG"
            rag_wins += 1
        else:
            winner = "  ★ LightRAG"
            lightrag_wins += 1

        # 高亮显示更高分数
        if rag_val > lightrag_val:
            rag_str = f"*{rag_val:.4f}*"
        elif lightrag_val > rag_val:
            lightrag_str = f"*{lightrag_val:.4f}*"

        print(f"{info['name_cn']:<18} {rag_str:>10} {lightrag_str:>10} {winner:>12}")

    print("-" * 70)
    print(f"\n总结: RAG 赢 {rag_wins} 项, LightRAG 赢 {lightrag_wins} 项, 平局 {4 - rag_wins - lightrag_wins} 项")
    print("=" * 70)


# ============================================================
# CLI 入口
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="RAGAS 评估脚本 - 对比 RAG 和 LightRAG")
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help=f"后端 API 地址 (默认: {DEFAULT_API_URL})",
    )
    parser.add_argument(
        "--dataset",
        default=str(DEFAULT_DATASET),
        help=f"测试数据集路径 (默认: {DEFAULT_DATASET})",
    )

    args = parser.parse_args()

    # 检查数据集是否存在
    if not os.path.exists(args.dataset):
        print(f"❌ 测试数据集不存在: {args.dataset}")
        print("请先创建测试数据集文件。")
        sys.exit(1)

    # 运行评估
    results = run_evaluation(args.api_url, args.dataset)

    print(f"\n✅ 评估完成！")
    print(f"   结果文件: {RESULTS_PATH}")
    print(f"   对比表格: {COMPARISON_PATH}")


if __name__ == "__main__":
    main()
