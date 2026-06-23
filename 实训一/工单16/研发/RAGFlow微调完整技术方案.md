# RAGFlow VLM 微调完整技术方案

## 一、项目概述

本项目基于 RAGFlow 平台的专利文档问答数据，对 Qwen2-VL-2B-Instruct 视觉语言模型进行 QLoRA 微调，使其具备理解专利 PDF 图纸并回答工业类问题的能力。整个流程分为四个阶段：**图片提取 → 数据集构建 → 模型训练 → 效果评估**。

硬件环境为 RTX 4060（8GB 显存），运行于 WSL 的 Ubuntu 环境，使用 LLaMA-Factory 作为训练框架。

---

## 二、数据来源

原始数据来自 RAGFlow 平台的专利问答库，包含以下内容：

| 内容 | 路径 | 规模 |
|------|------|------|
| 问题文件 | `original_problems/questions.jsonl` | 10,096 条 |
| 专利 PDF 文档 | `original_problems/documents/*.pdf` | 1,700 份 |

每条问题的数据格式如下：

```json
{
  "question": "在文件中第7页的图片中，部件4相对于部件5在图片中的位置关系是？",
  "document": "CN100342976C.pdf",
  "options": ["A. 部件4位于部件5的左侧", "B. 部件4位于部件5的右侧", ...],
  "answer": "A",
  "group": 2
}
```

其中 `group` 字段标识问题类型：

- **group 1**：文本理解题 — 仅需阅读 PDF 文本即可回答，不依赖图纸
- **group 2**：图纸位置题 — 需要观察 PDF 中的具体图纸来判断部件位置关系
- **group 3**：图纸推理题 — 需要结合图纸进行逻辑推理才能回答

---

## 三、第一阶段：从专利 PDF 中提取页面图片

### 3.1 设计思路

并非所有问题都需要图纸，group 1 的纯文本题只需封面即可。对于 group 2 和 group 3，题目中明确标注了"第X页"，因此只需提取题目所引用的特定页码，而非整份 PDF。这种按需提取策略大幅减少了图片数量和存储开销。

### 3.2 脚本：extract_images.py

**核心逻辑**：

1. 扫描 `questions.jsonl`，用正则 `第(\d+)页` 提取每道题引用的页码
2. 对于未引用页码的 group 1 题目，默认提取第 1 页（封面）
3. 使用 PyMuPDF（fitz）以 200 DPI 渲染 PDF 页面为 PNG 图片
4. 输出目录结构：`images/{文档名}/page_{页码}.png`
5. 使用 `ProcessPoolExecutor` 并行处理（4 个进程），提升效率

**关键参数**：

| 参数 | 值 | 说明 |
|------|-----|------|
| DPI | 200 | 平衡图片质量与文件大小，足够训练使用 |
| MAX_WORKERS | 4 | 并行进程数 |
| 图片格式 | PNG | 无损压缩，避免训练时引入伪影 |

**输出结果**：

- 处理了 1,700 个 PDF 文档，提取了约 3,400+ 张页面图片
- 每张图片约 400×565 像素，对应约 280 个视觉 token
- 图片保存在 `/home/su/ragflow_vlm_data/images/` 目录下

---

## 四、第二阶段：构建 VLM 微调数据集

### 4.1 数据格式设计

LLaMA-Factory 要求 ShareGPT 格式的对话数据，每条样本包含 `messages`（对话轮次）和 `images`（图片路径列表）两个字段。

**样本结构示例**：

```json
{
  "messages": [
    {"content": "<image>在文件中第7页的图片中，部件4相对于部件5在图片中的位置关系是？\n\n选项：\nA. 部件4位于部件5的左侧\nB. 部件4位于部件5的右侧\nC. 部件4位于部件5的上方\nD. 部件4位于部件5的下方", "role": "user"},
    {"content": "A\nA. 部件4位于部件5的左侧", "role": "assistant"}
  ],
  "images": ["/home/su/ragflow_vlm_data/images/CN100342976C/page_07.png"]
}
```

**设计要点**：

- 在 user 内容中使用 `<image>` 标记告诉模型需要查看图片
- assistant 回复包含答案字母和完整选项文本，帮助模型学习完整的答题格式
- 图片路径使用绝对路径，因为 LLaMA-Factory 在 WSL 中运行

### 4.2 脚本：build_dataset.py

**处理流程**：

1. 加载 `questions.jsonl`（10,096 条）
2. 为每道题匹配对应的图片文件
3. 按照 ShareGPT 格式构建微调样本
4. 按 8:1:1 比例随机划分训练集/验证集/测试集
5. 生成 `dataset_info.json` 注册信息供 LLaMA-Factory 读取

**划分结果**：

| 数据集 | 样本数 | 用途 |
|--------|--------|------|
| train.jsonl | 8,076 条 | 模型训练 |
| val.jsonl | 1,009 条 | 训练过程验证 |
| test.jsonl | 1,011 条 | 最终效果评估 |

**dataset_info.json 注册配置**：

数据集在 LLaMA-Factory 中注册为三个名称（`vlm_industrial_qa_train`、`vlm_industrial_qa_val`、`vlm_industrial_qa_test`），使用 `sharegpt` 格式，角色标签映射为 `user`/`assistant`，图片列名为 `images`。

---

## 五、第三阶段：QLoRA 微调训练

### 5.1 为什么选择 QLoRA

在 8GB 显存的 RTX 4060 上全量微调 2B 参数的模型是不可行的。QLoRA 通过以下技术组合解决了这个问题：

- **4-bit 量化（NF4）**：将基座模型权重压缩到 4-bit，显存占用从约 4GB 降至约 1.5GB
- **LoRA 适配器**：仅训练低秩分解的增量参数，而非全部参数，大幅减少可训练参数量
- **梯度检查点**：用计算换显存，前向传播时不保存中间激活值，反向传播时重新计算

### 5.2 LoRA 配置详解

| 参数 | 值 | 说明 |
|------|-----|------|
| lora_rank (r) | 16 | 低秩分解的秩，越大表达力越强但显存越多 |
| lora_alpha | 32 | 缩放因子，通常为 rank 的 2 倍 |
| lora_target | all | 对所有线性层应用 LoRA（Qwen2-VL 的 attn、mlp、gate） |
| lora_dropout | 0.05 | 防止过拟合的随机丢弃率 |
| quantization_bit | 4 | 4-bit NF4 量化 |
| quantization_method | bitsandbytes | 使用 bitsandbytes 库进行量化 |

**可训练参数量**：约 3,000 万（占总参数的 ~1.5%），显存占用约 3-4GB。

### 5.3 训练超参数

项目经历了三个配置版本的迭代优化：

| 参数 | v1 (qlora_config) | v2 (qlora_config_v2) | v3 (qlora_config_v3) |
|------|--------------------|-----------------------|-----------------------|
| cutoff_len | 512 | 600 | 600 |
| max_samples | 10,000 | 2,000 | — |
| num_train_epochs | 3.0 | 1.0 | — |
| max_steps | — | — | 250 |
| warmup_ratio | 0.1 | — | — |
| warmup_steps | — | 10 | 10 |
| per_device_batch_size | 1 | 1 | 1 |
| gradient_accumulation | 8 | 8 | 8 |
| effective batch | 8 | 8 | 8 |
| eval_strategy | steps (500) | no | no |
| output_dir | saves | saves_v2 | saves_v3 |

**版本迭代原因**：

- **v1 → v2**：cutoff_len 从 512 提升到 600（因图片 token 约 280 个，512 不够容纳图片+文本）；max_samples 从 10000 降到 2000 减少显存压力；epoch 从 3 降到 1 防止过拟合；关闭 eval 避免中途评估卡住
- **v2 → v3**：改用 v1 格式的配置（peft_config/quant_config 分离写法），用 max_steps 250 替代 epoch 控制

### 5.4 环境要求

- 虚拟环境：`/home/su/llamafactory_env/`（Python 环境）
- 模型权重：`/home/su/llamafactory_env/models/Qwen2-VL-2B-Instruct`
- 额外依赖：`bitsandbytes` 需手动安装（pip install bitsandbytes）
- WebUI 启动：`llamafactory-cli webui --host 0.0.0.0 --port 7860`

### 5.5 启动方式

**方式一：WebUI（推荐）**

```bash
bash launch_webui.sh
# 浏览器访问 http://localhost:7860
# 在 WebUI 中选择数据集、配置参数、点击训练
```

WebUI 方式更直观可靠，能自动处理一些配置细节，是工单16最终采用的方式。

**方式二：命令行**

```bash
# v1 配置
bash launch_train.sh
# 或 v2 配置
bash launch_train_v2.sh
```

### 5.6 DeepSpeed 配置

`llamaboard_cache/` 目录下缓存了四种 DeepSpeed ZeRO 配置，由 LLaMA-Factory WebUI 自动生成：

| 配置文件 | ZeRO Stage | CPU Offload | 说明 |
|----------|-----------|-------------|------|
| ds_z2_config.json | Stage 2 | 无 | 优化器状态分片 |
| ds_z2_offload_config.json | Stage 2 | 优化器 offload 到 CPU | 减少显存占用 |
| ds_z3_config.json | Stage 3 | 无 | 优化器+梯度+参数全分片 |
| ds_z3_offload_config.json | Stage 3 | 全部 offload 到 CPU | 最大程度节省显存 |

对于单卡 8GB 显存的 RTX 4060，推荐使用 **ZeRO Stage 2 + CPU Offload**，在显存和速度间取得平衡。

### 5.7 常见问题与经验

- **训练"卡住"**：通常不是真的卡住，而是某个 batch 中存在超长序列。先用 `nvidia-smi` 查看 GPU 利用率，如果显存未爆且利用率正常则耐心等待
- **WebUI 比 CLI 可靠**：旧格式 YAML 可能缺少某些隐藏标志导致静默退出，WebUI 会自动补全
- **bitsandbytes 兼容性**：需要与 CUDA 版本匹配，安装后用 `python -c "import bitsandbytes"` 验证
- **cutoff_len 不够**：图片 token 约 280 个，加上问题和选项文本，600 是比较安全的下限

---

## 六、第四阶段：效果评估

### 6.1 评估脚本：evaluate.py

评估脚本对比**基座模型**（微调前）和**微调模型**（微调后）在测试集上的表现。

**评估流程**：

1. 加载测试集，随机抽样 300 条（全量太慢）
2. 加载基座模型（4-bit 量化），逐条推理，记录答案准确率
3. 释放显存，加载微调模型（基座 + LoRA 权重），重复推理
4. 对比两者在总准确率和各 group 上的表现差异

**推理参数**：

| 参数 | 值 | 说明 |
|------|-----|------|
| MAX_NEW_TOKENS | 50 | 最大生成长度（选择题只需几个 token） |
| do_sample | False | 贪心解码，保证结果可复现 |
| temperature | 0.01 | 接近 0 的温度，几乎确定性输出 |
| top_k | 1 | 只保留概率最高的 token |
| top_p | 0.001 | 极小的核采样范围 |

**答案提取策略**：

从模型输出中用正则匹配开头的单个字母（A/B/C/D）或 `A.`/`A、` 格式。匹配不到则视为预测错误。

**输出文件**：

| 文件 | 内容 |
|------|------|
| `evaluation_report.json` | 完整评估报告（基座 vs 微调的准确率对比） |
| `error_analysis.json` | 错误样本分析（基座和微调各取前 10 个错误） |

### 6.2 评估指标

评估从两个维度分析效果：

- **总准确率**：所有 group 的综合表现
- **分组准确率**：分别统计 group 1（文本理解）、group 2（图纸位置）、group 3（图纸推理）的准确率

理想情况下，微调模型应在 group 2 和 group 3 上有显著提升，因为这些题目需要视觉理解能力，而基座模型从未见过这类工业专利图纸。

---

## 七、完整文件清单

| 文件 | 类型 | 功能 |
|------|------|------|
| `extract_images.py` | Python 脚本 | 从 PDF 提取页面图片 |
| `build_dataset.py` | Python 脚本 | 构建 LLaMA-Factory 格式数据集 |
| `evaluate.py` | Python 脚本 | 基座 vs 微调模型效果评估 |
| `qlora_config.yaml` | YAML 配置 | v1 版 QLoRA 训练参数 |
| `qlora_config_v2.yaml` | YAML 配置 | v2 版 QLoRA 训练参数（改进） |
| `qlora_config_v3.yaml` | YAML 配置 | v3 版 QLoRA 训练参数（v1 格式） |
| `launch_train.sh` | Shell 脚本 | 命令行启动 v1 训练 |
| `launch_train_v2.sh` | Shell 脚本 | 命令行启动 v2 训练 |
| `launch_webui.sh` | Shell 脚本 | 启动 LLaMA-Factory WebUI |
| `llamaboard_cache/ds_z2_config.json` | JSON 配置 | DeepSpeed ZeRO Stage 2 |
| `llamaboard_cache/ds_z2_offload_config.json` | JSON 配置 | DeepSpeed ZeRO Stage 2 + CPU Offload |
| `llamaboard_cache/ds_z3_config.json` | JSON 配置 | DeepSpeed ZeRO Stage 3 |
| `llamaboard_cache/ds_z3_offload_config.json` | JSON 配置 | DeepSpeed ZeRO Stage 3 + CPU Offload |

---

## 八、数据流转路径

```
原始数据
  questions.jsonl (10,096条) + documents/*.pdf (1,700份)
        │
        ▼
  ┌─ extract_images.py ─┐
  │  解析问题中的页码引用  │
  │  PyMuPDF 渲染PDF页面  │
  │  200 DPI 输出PNG     │
  └──────────────────────┘
        │
        ▼
  images/{文档名}/page_{页码}.png  (~3,400张)
        │
        ▼
  ┌─ build_dataset.py ──┐
  │  匹配题目与图片       │
  │  构建ShareGPT对话格式 │
  │  8:1:1划分数据集      │
  │  生成dataset_info.json│
  └──────────────────────┘
        │
        ▼
  dataset/
    ├── train.jsonl     (8,076条)
    ├── val.jsonl       (1,009条)
    ├── test.jsonl      (1,011条)
    └── dataset_info.json
        │
        ▼
  ┌─ LLaMA-Factory ─────┐
  │  QLoRA微调            │
  │  Qwen2-VL-2B + NF4   │
  │  LoRA r=16, α=32     │
  │  RTX 4060 8GB        │
  └──────────────────────┘
        │
        ▼
  saves/  (LoRA 适配器权重)
        │
        ▼
  ┌─ evaluate.py ───────┐
  │  抽样300条测试        │
  │  基座 vs 微调对比     │
  │  分group准确率统计    │
  └──────────────────────┘
        │
        ▼
  evaluation_report.json + error_analysis.json
```

---

## 九、技术选型说明

| 决策点 | 选择 | 原因 |
|--------|------|------|
| 基座模型 | Qwen2-VL-2B-Instruct | 2B 参数量适合 8GB 显存；Qwen2-VL 对中文和图表理解能力强 |
| 微调方法 | QLoRA (4-bit NF4) | 8GB 显存唯一可行方案，显存占用从 ~4GB 降至 ~1.5GB |
| 训练框架 | LLaMA-Factory | 提供 WebUI + 命令行双模式，对 Qwen2-VL 原生支持 |
| 图片提取 | PyMuPDF (fitz) | 轻量级 PDF 处理，支持按页渲染，无需 OCR |
| 量化工具 | bitsandbytes | HuggingFace 生态标准量化方案，与 transformers 深度集成 |
| 评估方式 | 答案字母匹配 | 选择题格式，直接比对 A/B/C/D 即可，简单可靠 |

---

## 十、后续优化方向

1. **更长的序列支持**：如果 GPU 显存允许，可将 cutoff_len 提升到 800-1024，容纳更多上下文
2. **数据增强**：对同一问题生成不同表述的 prompt，增加训练多样性
3. **多轮对话**：将单轮 QA 扩展为多轮对话格式，提升模型的上下文理解能力
4. **合并推理**：训练完成后使用 `llamafactory-cli export` 将 LoRA 权重合并到基座模型，获得独立的微调模型
5. **量化导出**：合并后的模型可进一步 GPTQ/AWQ 量化，部署到更轻量的推理环境
