# -*- coding: utf-8 -*-
# !/usr/bin/env python
# -*- coding: utf-8 -*-
"""
招股说明书问答系统 - 嵌入模型完整微调脚本
功能：
1. 从文档和查询处理器自动生成训练数据（问答对）
2. 加载预训练嵌入模型
3. 定义损失函数（MultipleNegativesRankingLoss）
4. 配置训练参数
5. 创建评估器（语义相似度评估）
6. 微调前评估模型基线
7. 执行微调训练
8. 微调后评估模型效果
9. 保存微调模型并更新配置
"""

import os
import sys
import json
import re
import random
from pathlib import Path
from typing import List, Dict, Tuple
import numpy as np
from tqdm import tqdm
# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from sentence_transformers import SentenceTransformer, InputExample, losses, evaluation
from torch.utils.data import DataLoader
from sklearn.metrics.pairwise import cosine_similarity

# ============================================================
# 配置区域
# ============================================================

# 模型路径（使用项目中已配置的模型）
ORIGINAL_MODEL_PATH = r"C:\Users\23672\Desktop\模型\m3e-base"
FINETUNED_MODEL_DIR = "./finetuned_model"

# 数据路径
DATA_DIR = Path("./data")
FAISS_INDEX_PATH = Path("./data/faiss_index")
TRAIN_DATA_FILE = "./finetune_data/train.jsonl"
EVAL_DATA_FILE = "./finetune_data/eval.jsonl"

# 训练参数
EPOCHS = 3
BATCH_SIZE = 8
LEARNING_RATE = 2e-5
WARMUP_STEPS = 100
EVALUATION_STEPS = 500

# 评估参数
EVAL_TOP_K = 5
TEST_QUERIES = [
    "公司2023年的营业收入是多少？",
    "公司面临的主要风险因素有哪些？",
    "公司的核心技术是什么？",
    "公司的实际控制人是谁？",
    "公司的主要产品有哪些？",
]


# ============================================================
# 第一步：数据集生成（从文档中自动生成问答对）
# ============================================================

class DatasetGenerator:
    """从招股说明书文档自动生成微调所需的问答对"""

    def __init__(self, chunks_file: str = None):
        self.chunks = []
        self.query_processor = None
        if chunks_file and os.path.exists(chunks_file):
            self._load_chunks(chunks_file)
        else:
            self._load_chunks_from_index()

    def _load_chunks_from_index(self):
        """从已有的FAISS索引中加载文本块"""
        chunks_pkl = FAISS_INDEX_PATH / "chunks.pkl"
        if chunks_pkl.exists():
            import pickle
            with open(chunks_pkl, "rb") as f:
                self.chunks = pickle.load(f)
            print(f"✓ 从索引加载了 {len(self.chunks)} 个文本块")
        else:
            print("⚠ 未找到索引文件，将重新加载PDF文档...")
            from document_loader import prepare_documents
            self.chunks = prepare_documents()

    def _load_chunks(self, chunks_file: str):
        import pickle
        with open(chunks_file, "rb") as f:
            self.chunks = pickle.load(f)
        print(f"✓ 从文件加载了 {len(self.chunks)} 个文本块")

    def generate_qa_pairs(self, max_pairs: int = 500) -> List[Dict]:
        """
        从文档块自动生成问答对
        返回格式: [{"query": "问题", "positive": "相关段落", "negative": "不相关段落"}, ...]
        """
        qa_pairs = []

        # 预定义的问题模板（针对招股说明书）
        templates = [
            # 财务类
            (r"营业收入.*?(\d+\.?\d*)\s*万元", "公司{year}年的营业收入是多少？"),
            (r"净利润.*?(\d+\.?\d*)\s*万元", "公司{year}年的净利润是多少？"),
            (r"归属于母公司所有者的净利润.*?(\d+\.?\d*)\s*万元", "公司{year}年的归母净利润是多少？"),
            (r"研发投入.*?(\d+\.?\d*)\s*万元", "公司{year}年的研发投入是多少？"),
            # 风险类
            (r"风险.*?(\w+风险)", "公司面临的主要{risk}有哪些？"),
            (r"（[^）]+）风险", "公司面临的主要风险因素是什么？"),
            # 产品/技术类
            (r"主要产品包括([^。]+)", "公司的主要产品有哪些？"),
            (r"核心技术([^。]+)", "公司的核心技术是什么？"),
            (r"掌握了([^。]+技术)", "公司掌握了哪些核心技术？"),
            # 公司信息类
            (r"控股股东[为是](\S+)", "公司的控股股东是谁？"),
            (r"实际控制人[为是](\S+)", "公司的实际控制人是谁？"),
            (r"注册资本[为是](\d+\.?\d*)\s*万元", "公司的注册资本是多少？"),
        ]

        # 为每个块生成候选问答对
        for chunk in self.chunks:
            content = chunk.get("content", "")
            page = chunk.get("page", 0)
            source = chunk.get("source", "")

            # 尝试匹配模板
            for pattern, query_template in templates:
                match = re.search(pattern, content)
                if match:
                    # 提取变量
                    if "{year}" in query_template:
                        year_match = re.search(r"(\d{4})年", content)
                        year = year_match.group(1) if year_match else "2023"
                        query = query_template.format(year=year)
                    elif "{risk}" in query_template:
                        risk = match.group(1) if "风险" in query_template else "风险"
                        query = query_template.format(risk=risk)
                    else:
                        query = query_template

                    # 使用匹配到的整个段落作为正样本
                    positive = content[:500]  # 限制长度

                    # 随机选择一个不相关的块作为负样本
                    negative_chunks = [c for c in self.chunks if c.get("chunk_id") != chunk.get("chunk_id")]
                    if negative_chunks:
                        negative = random.choice(negative_chunks).get("content", "")[:500]
                    else:
                        negative = ""

                    qa_pairs.append({
                        "query": query,
                        "positive": positive,
                        "negative": negative,
                        "page": page,
                        "source": source
                    })

                    if len(qa_pairs) >= max_pairs:
                        break

            if len(qa_pairs) >= max_pairs:
                break

        print(f"✓ 生成了 {len(qa_pairs)} 个问答对")
        return qa_pairs[:max_pairs]

    def save_qa_pairs(self, qa_pairs: List[Dict], train_file: str, eval_file: str, eval_ratio: float = 0.2):
        """保存问答对为训练集和评估集"""
        os.makedirs(os.path.dirname(train_file), exist_ok=True)

        random.shuffle(qa_pairs)
        split_idx = int(len(qa_pairs) * (1 - eval_ratio))

        train_pairs = qa_pairs[:split_idx]
        eval_pairs = qa_pairs[split_idx:]

        # 保存训练集
        with open(train_file, "w", encoding="utf-8") as f:
            for pair in train_pairs:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")

        # 保存评估集
        with open(eval_file, "w", encoding="utf-8") as f:
            for pair in eval_pairs:
                f.write(json.dumps(pair, ensure_ascii=False) + "\n")

        print(f"✓ 训练集: {len(train_pairs)} 条 -> {train_file}")
        print(f"✓ 评估集: {len(eval_pairs)} 条 -> {eval_file}")


# ============================================================
# 第二步：数据集与模型加载
# ============================================================

class DataLoaderBuilder:
    """构建微调所需的数据加载器和评估器"""

    @staticmethod
    def load_qa_pairs(file_path: str) -> List[Dict]:
        """从JSONL文件加载问答对"""
        pairs = []
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    pairs.append(json.loads(line))
        print(f"✓ 从 {file_path} 加载了 {len(pairs)} 个问答对")
        return pairs

    @staticmethod
    def build_train_dataloader(pairs: List[Dict], batch_size: int = BATCH_SIZE) -> DataLoader:
        """构建训练数据加载器（使用InputExample格式）"""
        train_examples = []
        for pair in pairs:
            # 使用 query 和 positive 作为正样本对
            train_examples.append(InputExample(texts=[pair["query"], pair["positive"]]))
            # 可选：添加 hard negative（如果提供了negative字段）
            if pair.get("negative"):
                train_examples.append(InputExample(texts=[pair["query"], pair["negative"]]))

        dataloader = DataLoader(train_examples, shuffle=True, batch_size=batch_size)
        print(f"✓ 训练数据加载器: {len(train_examples)} 个样本, {batch_size} batch size")
        return dataloader


# ============================================================
# 第三步：定义损失函数
# ============================================================

def create_loss_function(model: SentenceTransformer) -> losses.MultipleNegativesRankingLoss:
    """
    创建 MultipleNegativesRankingLoss
    这是针对检索任务最常用的损失函数，能够最大化正样本对的相似度，
    同时最小化负样本对的相似度。
    """
    loss = losses.MultipleNegativesRankingLoss(model)
    print("✓ 损失函数: MultipleNegativesRankingLoss")
    return loss


# ============================================================
# 第四步：定义训练参数
# ============================================================

class TrainingConfig:
    """训练参数配置"""

    def __init__(self):
        self.epochs = EPOCHS
        self.batch_size = BATCH_SIZE
        self.learning_rate = LEARNING_RATE
        self.warmup_steps = WARMUP_STEPS
        self.evaluation_steps = EVALUATION_STEPS
        self.output_path = FINETUNED_MODEL_DIR
        self.save_best_model = True
        self.use_amp = False  # 是否使用混合精度训练
        self.optimizer_params = {'lr': LEARNING_RATE}

    def to_dict(self) -> Dict:
        return {
            "epochs": self.epochs,
            "batch_size": self.batch_size,
            "learning_rate": self.learning_rate,
            "warmup_steps": self.warmup_steps,
            "evaluation_steps": self.evaluation_steps,
            "output_path": self.output_path,
        }

    def print_config(self):
        print("\n" + "=" * 50)
        print("训练参数配置")
        print("=" * 50)
        for k, v in self.to_dict().items():
            print(f"  {k}: {v}")
        print("=" * 50)


# ============================================================
# 第五步：创建评估器
# ============================================================

class EmbeddingEvaluator:
    """
    嵌入模型评估器
    评估指标：检索准确率（Recall@K）、平均相似度等
    """

    def __init__(self, model: SentenceTransformer):
        self.model = model

    def evaluate_retrieval(self, test_queries: List[str], test_docs: List[str], top_k: int = EVAL_TOP_K) -> Dict:
        """
        评估检索准确率
        test_queries: 查询列表
        test_docs: 文档列表（每个查询对应的正确文档）
        """
        # 编码所有查询和文档
        query_embeddings = self.model.encode(test_queries, convert_to_numpy=True)
        doc_embeddings = self.model.encode(test_docs, convert_to_numpy=True)

        # 计算相似度矩阵
        similarity_matrix = cosine_similarity(query_embeddings, doc_embeddings)

        # 计算 Recall@K
        recall_at_k = {}
        for k in [1, 3, 5]:
            correct = 0
            for i, sims in enumerate(similarity_matrix):
                top_k_indices = np.argsort(sims)[-k:][::-1]
                if i in top_k_indices:
                    correct += 1
            recall_at_k[f"Recall@{k}"] = correct / len(test_queries)

        # 计算平均相似度（对角线）
        avg_similarity = np.mean([similarity_matrix[i, i] for i in range(len(test_queries))])
        recall_at_k["avg_similarity"] = avg_similarity

        return recall_at_k

    def evaluate_on_qa_pairs(self, qa_pairs: List[Dict]) -> Dict:
        """在问答对数据集上评估"""
        queries = [p["query"] for p in qa_pairs]
        positives = [p["positive"] for p in qa_pairs]

        return self.evaluate_retrieval(queries, positives)

    def print_evaluation(self, eval_result: Dict, title: str = "评估结果"):
        """打印评估结果"""
        print(f"\n{title}")
        print("-" * 40)
        for metric, value in eval_result.items():
            if metric.startswith("Recall"):
                print(f"  {metric}: {value:.4f} ({value * 100:.2f}%)")
            else:
                print(f"  {metric}: {value:.4f}")


# ============================================================
# 第六步：微调前评估模型（基线）
# ============================================================

def evaluate_baseline(model_path: str, eval_pairs: List[Dict]) -> Dict:
    """微调前评估模型性能"""
    print("\n" + "=" * 60)
    print("🔍 微调前评估（基线模型）")
    print("=" * 60)

    model = SentenceTransformer(model_path)
    evaluator = EmbeddingEvaluator(model)

    # 使用评估集进行评估
    result = evaluator.evaluate_on_qa_pairs(eval_pairs)
    evaluator.print_evaluation(result, "基线模型性能")

    return result


# ============================================================
# 第七步：执行微调训练
# ============================================================

def run_finetuning(model, train_dataloader, loss_fn, config: TrainingConfig):
    """手动训练循环 - 绕过 transformers 版本兼容问题"""
    print("\n" + "=" * 60)
    print("🚀 开始微调训练（手动循环）")
    print("=" * 60)
    config.print_config()

    import torch
    from torch.optim import AdamW
    from tqdm import tqdm
    import os
    from torch.utils.data import DataLoader as TorchDataLoader

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"使用设备: {device}")
    model.to(device)
    model.train()

    os.makedirs(config.output_path, exist_ok=True)
    optimizer = AdamW(model.parameters(), lr=config.learning_rate)

    # 自定义 collate 函数，将 InputExample 列表转为 (queries, positives) 字符串列表
    def collate_input_examples(batch):
        queries = [ex.texts[0] for ex in batch]
        positives = [ex.texts[1] for ex in batch]
        return queries, positives

    # 重新构建 DataLoader，使用自定义 collate_fn
    train_loader = TorchDataLoader(
        train_dataloader.dataset,
        batch_size=config.batch_size,
        shuffle=True,
        collate_fn=collate_input_examples
    )

    for epoch in range(config.epochs):
        epoch_loss = 0.0
        progress_bar = tqdm(train_loader, desc=f"Epoch {epoch + 1}/{config.epochs}")

        for queries, positives in progress_bar:
            # 编码
            tok_q = model.tokenizer(queries, padding=True, truncation=True, return_tensors="pt", max_length=512)
            tok_p = model.tokenizer(positives, padding=True, truncation=True, return_tensors="pt", max_length=512)
            tok_q = {k: v.to(device) for k, v in tok_q.items()}
            tok_p = {k: v.to(device) for k, v in tok_p.items()}

            # 获取 embeddings
            emb_q = model(tok_q)['sentence_embedding']
            emb_p = model(tok_p)['sentence_embedding']

            # 归一化
            emb_q = torch.nn.functional.normalize(emb_q, p=2, dim=1)
            emb_p = torch.nn.functional.normalize(emb_p, p=2, dim=1)

            # 计算损失 (MultipleNegativesRankingLoss)
            scores = torch.matmul(emb_q, emb_p.t())
            labels = torch.arange(scores.size(0), device=device)
            loss = torch.nn.functional.cross_entropy(scores, labels)

            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

            epoch_loss += loss.item()
            progress_bar.set_postfix({"loss": loss.item()})

        avg_loss = epoch_loss / len(train_loader)
        print(f"Epoch {epoch + 1} 平均损失: {avg_loss:.4f}")

        # 保存检查点
        checkpoint_path = os.path.join(config.output_path, f"checkpoint_epoch_{epoch + 1}")
        os.makedirs(checkpoint_path, exist_ok=True)
        model.save(checkpoint_path)

    # 保存最终模型
    model.save(config.output_path)
    print(f"\n✓ 微调完成！模型已保存到: {config.output_path}")
    return model


# ============================================================
# 第八步：微调后评估模型
# ============================================================

def evaluate_finetuned(finetuned_path: str, eval_pairs: List[Dict], baseline_result: Dict = None) -> Dict:
    """微调后评估模型性能，并与基线对比"""
    print("\n" + "=" * 60)
    print("🔍 微调后评估（微调模型）")
    print("=" * 60)

    model = SentenceTransformer(finetuned_path)
    evaluator = EmbeddingEvaluator(model)

    # 使用相同的评估集进行评估
    result = evaluator.evaluate_on_qa_pairs(eval_pairs)
    evaluator.print_evaluation(result, "微调模型性能")

    # 与基线对比
    if baseline_result:
        print("\n📊 性能对比")
        print("-" * 40)
        for metric in ["Recall@1", "Recall@3", "Recall@5", "avg_similarity"]:
            if metric in result and metric in baseline_result:
                baseline = baseline_result[metric]
                finetuned = result[metric]
                diff = finetuned - baseline
                arrow = "↑" if diff > 0 else "↓" if diff < 0 else "→"
                print(f"  {metric}: {baseline:.4f} → {finetuned:.4f} ({arrow} {abs(diff):.4f})")

    return result


# ============================================================
# 第九步：保存配置并更新项目配置
# ============================================================

def update_project_config():
    """更新项目的 config.py，使用微调后的模型"""
    config_path = Path(__file__).parent / "config.py"
    if not config_path.exists():
        print("⚠ 未找到 config.py，请手动更新")
        return

    with open(config_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 备份原配置
    backup_path = config_path.with_suffix(".py.bak")
    with open(backup_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"✓ 已备份原配置到: {backup_path}")

    # 替换模型路径
    new_model_path = os.path.abspath(FINETUNED_MODEL_DIR).replace("\\", "/")
    new_content = re.sub(
        r'EMBEDDINGS_MODEL = r?".*?"',
        f'EMBEDDINGS_MODEL = r"{new_model_path}"',
        content
    )

    with open(config_path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"✓ 已更新 config.py 中的 EMBEDDINGS_MODEL 为: {new_model_path}")
    print("  请重启系统以使新模型生效")


# ============================================================
# 主函数：完整微调流程
# ============================================================

def main():
    print("\n" + "=" * 80)
    print("🎯 招股说明书问答系统 - 嵌入模型完整微调流程")
    print("=" * 80)

    # -------------------- 步骤1：生成数据集 --------------------
    print("\n[步骤 1/8] 生成问答对数据集")
    print("-" * 50)

    generator = DatasetGenerator()
    qa_pairs = generator.generate_qa_pairs(max_pairs=500)
    generator.save_qa_pairs(qa_pairs, TRAIN_DATA_FILE, EVAL_DATA_FILE)

    # -------------------- 步骤2：加载数据集 --------------------
    print("\n[步骤 2/8] 加载训练集和评估集")
    print("-" * 50)

    train_pairs = DataLoaderBuilder.load_qa_pairs(TRAIN_DATA_FILE)
    eval_pairs = DataLoaderBuilder.load_qa_pairs(EVAL_DATA_FILE)

    # -------------------- 步骤3：加载模型 --------------------
    print("\n[步骤 3/8] 加载预训练嵌入模型")
    print("-" * 50)

    model = SentenceTransformer(ORIGINAL_MODEL_PATH)
    print(f"✓ 模型加载完成: {ORIGINAL_MODEL_PATH}")
    print(f"  模型维度: {model.get_sentence_embedding_dimension()}")

    # -------------------- 步骤4：构建数据加载器 --------------------
    print("\n[步骤 4/8] 构建训练数据加载器")
    print("-" * 50)

    train_dataloader = DataLoaderBuilder.build_train_dataloader(train_pairs, batch_size=BATCH_SIZE)

    # -------------------- 步骤5：定义损失函数 --------------------
    print("\n[步骤 5/8] 定义损失函数")
    print("-" * 50)

    loss_fn = create_loss_function(model)

    # -------------------- 步骤6：配置训练参数 --------------------
    print("\n[步骤 6/8] 配置训练参数")
    print("-" * 50)

    training_config = TrainingConfig()
    training_config.print_config()

    # -------------------- 步骤7：微调前评估（基线）--------------------
    baseline_result = evaluate_baseline(ORIGINAL_MODEL_PATH, eval_pairs)

    # -------------------- 步骤8：执行微调 --------------------
    print("\n[步骤 7/8] 执行微调训练")
    print("-" * 50)

    finetuned_model = run_finetuning(
        model=model,
        train_dataloader=train_dataloader,
        loss_fn=loss_fn,

        config=training_config
    )

    # -------------------- 步骤9：微调后评估 --------------------
    print("\n[步骤 8/8] 微调后评估")
    print("-" * 50)

    finetuned_result = evaluate_finetuned(FINETUNED_MODEL_DIR, eval_pairs, baseline_result)

    # -------------------- 步骤10：更新项目配置 --------------------
    print("\n[额外步骤] 更新项目配置")
    print("-" * 50)

    update_project_config()

    # -------------------- 总结 --------------------
    print("\n" + "=" * 80)
    print("✅ 微调完成！")
    print("=" * 80)
    print(f"📁 微调模型保存位置: {os.path.abspath(FINETUNED_MODEL_DIR)}")
    print(f"📊 训练数据: {TRAIN_DATA_FILE}")
    print(f"📊 评估数据: {EVAL_DATA_FILE}")
    print("\n🚀 下一步:")
    print("  1. 重启问答系统: python api_server.py")
    print("  2. 或运行: python 1.py")
    print("  3. 测试微调效果: python test_finetune.py")
    print("=" * 80)


# ============================================================
# 独立测试脚本入口
# ============================================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="嵌入模型微调工具")
    parser.add_argument("--only-generate", action="store_true", help="仅生成数据集，不进行训练")
    parser.add_argument("--only-evaluate", action="store_true", help="仅评估模型，不进行训练")
    parser.add_argument("--model-path", type=str, default=None, help="指定评估的模型路径")
    args = parser.parse_args()

    if args.only_generate:
        print("仅生成数据集模式")
        generator = DatasetGenerator()
        qa_pairs = generator.generate_qa_pairs(max_pairs=500)
        generator.save_qa_pairs(qa_pairs, TRAIN_DATA_FILE, EVAL_DATA_FILE)
        print("数据集生成完成")
    elif args.only_evaluate:
        model_path = args.model_path or ORIGINAL_MODEL_PATH
        eval_pairs = DataLoaderBuilder.load_qa_pairs(EVAL_DATA_FILE)
        evaluate_baseline(model_path, eval_pairs)
    else:
        main()