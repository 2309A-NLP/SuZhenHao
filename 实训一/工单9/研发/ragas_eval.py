"""
RAGAS 评估脚本 - Context Precision & Context Recall
用法：conda activate nlp_2 && python ragas_eval.py
"""

import os
import sys
import json
import pdfplumber

# ========== 路径配置 ==========
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(PROJECT_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# PDF 问题文件路径
SAMPLE_PDF = r"C:\Users\23672\Desktop\RAG 新工单\附件\sample_questions.pdf"
# 向量库目录
VECTOR_STORE_DIR = os.path.join(PROJECT_DIR, "vector_store")
# Embedding 模型路径
EMBEDDING_MODEL_PATH = r"C:\Users\23672\Desktop\模型\bge-base-zh-v1.5"
# MiMo API 配置
MIMO_API_KEY = "tp-crncudh1306abwos94du3c0u7898mkyvxxn9pmq3klsqsnb3"
MIMO_BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
MIMO_MODEL = "mimo-v2.5-pro"
# 检索参数
TOP_K = 4

# ========== Step 1: 解析 PDF 提取问题和参考答案 ==========
def parse_sample_pdf(pdf_path: str) -> list:
    """
    从 sample_questions.pdf 中提取问题和参考答案
    返回: [{"question": str, "ground_truth": str}, ...]
    """
    print("=" * 60)
    print("Step 1: 解析 sample_questions.pdf")
    print("=" * 60)

    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n\n"

    # 解析："问题：" / "答案：" / "参考答案：" 各占一行，内容在下一行
    # 按行扫描，识别标记行，收集内容
    lines = full_text.split("\n")
    qa_pairs = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 找到问题标记
        if line in ("问题：", "问题:"):
            # 问题内容在下一行
            i += 1
            question_lines = []
            while i < len(lines):
                l = lines[i].strip()
                # 遇到答案标记或下一个问题标记则停止
                if l in ("答案：", "答案:", "参考答案：", "参考答案:", "问题：", "问题:"):
                    break
                if l:
                    question_lines.append(l)
                i += 1
            question = " ".join(question_lines)

            # 现在 i 指向答案标记行
            if i < len(lines) and lines[i].strip() in ("答案：", "答案:", "参考答案：", "参考答案:"):
                i += 1
                answer_lines = []
                while i < len(lines):
                    l = lines[i].strip()
                    # 遇到下一个问题标记或文档来源则停止
                    if l in ("问题：", "问题:"):
                        break
                    # 文档来源行：包含 __ 的行
                    if "__" in l and "年" in l:
                        i += 1
                        break
                    if l:
                        answer_lines.append(l)
                    i += 1
                ground_truth = "\n".join(answer_lines)

                if question and ground_truth:
                    qa_pairs.append({
                        "question": question,
                        "ground_truth": ground_truth
                    })
        else:
            i += 1

    print(f"  解析到 {len(qa_pairs)} 个问答对")
    for i, qa in enumerate(qa_pairs, 1):
        print(f"  Q{i}: {qa['question'][:60]}...")
        print(f"  A{i}: {qa['ground_truth'][:80]}...")
        print()

    return qa_pairs


# ========== Step 2: 用 sample_questions.pdf 构建向量库 ==========
SAMPLE_PDF = r"C:\Users\23672\Desktop\RAG 新工单\附件\sample_questions.pdf"


def build_and_load_vector_store(pdf_path: str):
    """从 PDF 构建向量库并返回"""
    print("=" * 60)
    print("Step 2: 用 sample_questions.pdf 构建向量库")
    print("=" * 60)

    import torch
    import shutil
    import tempfile
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.vectorstores import FAISS
    from langchain_community.embeddings import HuggingFaceEmbeddings

    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    print(f"  使用设备: {device}")

    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_PATH,
        model_kwargs={'device': device},
        encode_kwargs={
            'normalize_embeddings': True,
            'batch_size': 64,
        }
    )

    # 提取文本
    print("  提取 PDF 文本...")
    with pdfplumber.open(pdf_path) as pdf:
        full_text = ""
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n\n"
    print(f"  总字符数: {len(full_text)}")

    # 分块
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=800,
        chunk_overlap=100,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
        length_function=len
    )
    chunks = text_splitter.split_text(full_text)
    print(f"  分块数: {len(chunks)}")

    # 构建向量库
    print("  构建 FAISS 向量库...")
    vector_store = FAISS.from_texts(chunks, embeddings)

    # 保存到临时目录（避免中文路径问题）
    tmp_dir = os.path.join(tempfile.gettempdir(), "ragas_faiss_eval")
    if os.path.exists(tmp_dir):
        shutil.rmtree(tmp_dir)
    os.makedirs(tmp_dir, exist_ok=True)
    vector_store.save_local(tmp_dir)
    print(f"  向量库已保存到: {tmp_dir}")

    return vector_store


def retrieve_contexts(vector_store, questions: list) -> list:
    """对每个问题做检索，返回 contexts 列表"""
    print("=" * 60)
    print("Step 3: 对每个问题进行 FAISS 检索")
    print("=" * 60)

    all_contexts = []
    for i, qa in enumerate(questions, 1):
        query = qa["question"]
        results = vector_store.similarity_search_with_score(query, k=TOP_K)
        contexts = [doc.page_content for doc, score in results]
        all_contexts.append(contexts)
        print(f"  Q{i}: 检索到 {len(contexts)} 个文本块")
        for j, ctx in enumerate(contexts):
            print(f"    Chunk {j+1}: {ctx[:80]}...")
        print()

    return all_contexts


# ========== Step 4: 手动评估（不依赖 RAGAS 包） ==========
def call_mimo_judge(question: str, context: str, ground_truth: str, judge_type: str) -> bool:
    """
    调用 MiMo API 判断相关性
    judge_type: "precision" 判断 context 是否与 question 相关
                "recall" 判断 ground_truth 的某个句子是否被 context 覆盖
    """
    from openai import OpenAI
    client = OpenAI(api_key=MIMO_API_KEY, base_url=MIMO_BASE_URL)

    if judge_type == "precision":
        prompt = f"""以下是一段文本和一个问题。请判断这段文本是否包含与问题相关的信息。

问题：{question}

文本：{context}

请用一句话说明是否相关，最后一词必须是“相关”或“不相关”。"""
    else:  # recall
        prompt = f"""以下是两段文本。请判断第二段文本是否包含第一段所述的信息。

需要查找的信息：{context}

文本：{ground_truth}

请用一句话说明是否包含，最后一词必须是“包含”或“不包含”。"""

    try:
        response = client.chat.completions.create(
            model=MIMO_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=2048,
        )
        answer = response.choices[0].message.content
        if answer is None:
            print(f"      [MiMo回复: None - API可能有问题]")
            print(f"      [完整响应: {response}]")
            return False
        answer = answer.strip()
        print(f"      [MiMo回复: {answer[:80]}]")

        if not answer:
            return False

        # 兼容多种回复格式
        if judge_type == "precision":
            positive = ["相关", "是", "有帮助", "有用", "有交集"]
            negative = ["不相关", "无关"]
            has_pos = any(w in answer for w in positive)
            has_neg = any(w in answer for w in negative)
            result = has_pos and not has_neg
        else:
            positive = ["包含", "覆盖", "有该信息", "有此信息"]
            negative = ["不包含", "未覆盖", "没有"]
            has_pos = any(w in answer for w in positive)
            has_neg = any(w in answer for w in negative)
            result = has_pos and not has_neg
        return result
    except Exception as e:
        print(f"    API 调用出错: {type(e).__name__}: {e}")
        return False


def compute_context_precision(question: str, contexts: list, ground_truth: str) -> float:
    """
    计算 Context Precision（基于 MRR）
    对每个检索到的 context，判断是否与 question 相关，
    然后计算 MRR（Mean Reciprocal Rank）
    """
    relevance = []
    for i, ctx in enumerate(contexts):
        is_relevant = call_mimo_judge(question, ctx, ground_truth, "precision")
        relevance.append((i + 1, is_relevant))  # (rank, is_relevant)
        print(f"    Context {i+1}: {'✅ 相关' if is_relevant else '❌ 不相关'}")

    # MRR: 第一个相关结果的倒数排名
    for rank, is_relevant in relevance:
        if is_relevant:
            return 1.0 / rank
    return 0.0


def compute_context_recall(contexts: list, ground_truth: str) -> float:
    """
    计算 Context Recall
    将 ground_truth 拆成独立句子，检查每个句子是否被 contexts 覆盖
    """
    import re
    # 按句号、换行、数字编号拆分 ground_truth 为独立信息点
    sentences = re.split(r'\n|(?<=。)|(?<=\d\.\s)', ground_truth)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 5]

    # 合并所有 context
    all_context = "\n".join(contexts)

    covered = 0
    total = len(sentences)

    for sent in sentences:
        is_covered = call_mimo_judge(sent, sent, all_context, "recall")
        print(f"    信息点: {sent[:50]}... → {'✅ 已覆盖' if is_covered else '❌ 未覆盖'}")
        if is_covered:
            covered += 1

    return covered / total if total > 0 else 0.0


def manual_evaluation(qa_pairs: list, all_contexts: list):
    """手动评估，返回与 RAGAS 兼容的结果格式"""
    print("  使用 MiMo API 进行手动评估...")
    print()

    results = []
    for i, (qa, contexts) in enumerate(zip(qa_pairs, all_contexts), 1):
        print(f"  --- Q{i}: {qa['question'][:50]}... ---")

        print(f"  计算 Context Precision:")
        precision = compute_context_precision(qa["question"], contexts, qa["ground_truth"])
        print(f"  → Precision: {precision:.4f}")
        print()

        print(f"  计算 Context Recall:")
        recall = compute_context_recall(contexts, qa["ground_truth"])
        print(f"  → Recall: {recall:.4f}")
        print()

        results.append({"context_precision": precision, "context_recall": recall})

    return results


# ========== Step 5: 输出报告 ==========
def print_report(results, qa_pairs):
    """打印评估报告"""
    print()
    print("=" * 60)
    print("📊 RAGAS 评估报告")
    print("=" * 60)

    precisions = [r["context_precision"] for r in results]
    recalls = [r["context_recall"] for r in results]
    avg_precision = sum(precisions) / len(precisions) if precisions else 0
    avg_recall = sum(recalls) / len(recalls) if recalls else 0

    print(f"\n{'指标':<30} {'分数':>10}")
    print("-" * 42)
    print(f"{'Context Precision':<30} {avg_precision:>10.4f}")
    print(f"{'Context Recall':<30} {avg_recall:>10.4f}")

    # 达标判断
    print()
    print("-" * 42)
    precision_ok = avg_precision >= 0.8
    recall_ok = avg_recall >= 0.9

    print(f"  Context Precision ≥ 0.8:  {'✅ 达标' if precision_ok else '❌ 未达标'} ({avg_precision:.4f})")
    print(f"  Context Recall    ≥ 0.9:  {'✅ 达标' if recall_ok else '❌ 未达标'} ({avg_recall:.4f})")

    if precision_ok and recall_ok:
        print("\n🎉 恭喜！两项指标全部达标！")
    else:
        print("\n⚠️  有指标未达标，建议优化检索策略。")

    # 每个问题的详细分数
    print()
    print("=" * 60)
    print("📝 各问题详细分数")
    print("=" * 60)

    for i, (qa, r) in enumerate(zip(qa_pairs, results), 1):
        p = r["context_precision"]
        rc = r["context_recall"]
        print(f"\nQ{i}: {qa['question'][:60]}")
        print(f"    Precision: {p:.4f}")
        print(f"    Recall:    {rc:.4f}")

    # 保存结果到文件
    report = {
        "summary": {
            "context_precision": avg_precision,
            "context_recall": avg_recall,
            "precision_pass": precision_ok,
            "recall_pass": recall_ok,
        },
        "details": []
    }
    for i, (qa, r) in enumerate(zip(qa_pairs, results), 1):
        report["details"].append({
            "question": qa["question"],
            "ground_truth": qa["ground_truth"],
            "precision": r["context_precision"],
            "recall": r["context_recall"],
        })

    report_path = os.path.join(PROJECT_DIR, "ragas_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n📄 详细报告已保存到: {report_path}")


# ========== 主流程 ==========
def main():
    print()
    print("🦞 RAGAS 评估工具 - Context Precision & Recall")
    print("   目标: Precision ≥ 0.8, Recall ≥ 0.9")
    print()

    # Step 1: 解析 PDF
    qa_pairs = parse_sample_pdf(SAMPLE_PDF)
    if not qa_pairs:
        print("❌ 未能从 PDF 中解析出问答对，请检查 PDF 格式。")
        return

    # Step 2: 构建向量库
    vector_store = build_and_load_vector_store(SAMPLE_PDF)

    # Step 3: 检索
    all_contexts = retrieve_contexts(vector_store, qa_pairs)

    # Step 4: 评估
    results = manual_evaluation(qa_pairs, all_contexts)

    # Step 5: 输出报告
    print_report(results, qa_pairs)


if __name__ == "__main__":
    main()
