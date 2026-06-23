---
name: document-quality-assessment
description: >-
  Assesses document corpus quality: format distribution, PDF page type
  classification, length statistics, duplicate detection (MD5 + SimHash), and
  sensitive information scanning. Outputs structured JSON and HTML brief.
  Use when evaluating document folders, corpus quality, data cleaning prep,
  or when the user mentions DocumentQualityAssessmentSkill.
---

# DocumentQualityAssessmentSkill

对指定文件夹中的文档进行质量评估，输出结构化 JSON 报告与 HTML 简报。

## 快速开始

```bash
# 安装依赖（首次）
pip install -r .cursor/skills/document-quality-assessment/requirements.txt

# 运行评估（使用默认配置）
python .cursor/skills/document-quality-assessment/scripts/assess_documents.py \
  --input <文档目录> \
  --output-dir <输出目录>

# 指定配置文件
python .cursor/skills/document-quality-assessment/scripts/assess_documents.py \
  --input <文档目录> \
  --config .cursor/skills/document-quality-assessment/assessment_config.yaml
```

默认输出：
- `quality_report.json` — 完整结构化报告
- `quality_brief.html` — 可视化简报

## 工作流

```
评估进度：
- [ ] Step 1: 确认输入目录与输出目录
- [ ] Step 2: 安装依赖并运行 assess_documents.py
- [ ] Step 3: 检查 JSON 报告完整性
- [ ] Step 4: 在浏览器中预览 HTML 简报
- [ ] Step 5: 向用户汇报关键发现
```

### Step 1: 确认参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--input` | 待评估文档根目录 | 必填 |
| `--output-dir` | 报告输出目录 | `./quality_report` |
| `--config` | 配置文件路径 | `assessment_config.yaml` |
| `--simhash-threshold` | 覆盖SimHash汉明距离阈值 | 配置文件中的值 |
| `--context-chars` | 覆盖敏感信息上下文长度 | 配置文件中的值 |
| `--recursive` | 递归遍历子目录 | `true` |
| `--no-classify` | 跳过文档分类标签 | `false` |
| `--resume` | 从之前的JSON报告恢复 | 无 |

### Step 2: 执行评估

运行脚本后等待完成。大目录（>1000 文件）可能耗时数分钟。

脚本会显示进度条（需要 tqdm），支持 Ctrl+C 中断后从已保存的报告恢复。

若缺少依赖，先执行 `pip install -r requirements.txt`。

### Step 3: 验证输出

确认 JSON 包含以下顶层字段：

- `meta` — 扫描元信息（含配置参数记录）
- `format_distribution` — 格式分布统计
- `pdf_page_types` — PDF 页面类型识别
- `length_distribution` — 文档长度分布
- `duplicates` — 重复检测结果
- `sensitive_info` — 敏感信息检测
- `classification` — 文档分类标签

### Step 4: 汇报要点

向用户总结：

1. **格式分布**：主要文件类型及占比
2. **PDF 质量**：文字型/扫描型/混合型比例
3. **长度分布**：中位数、分位数、异常短/长文档
4. **重复情况**：精确重复组数、近似重复对数
5. **敏感信息**：命中数量及涉及文件（脱敏展示）
6. **分类标签**：各标签文件数量

## 功能模块说明

### 1. 格式分布统计

遍历目录，按扩展名统计文件数量与占比。无扩展名文件归类为 `(no_extension)`。

### 2. PDF 页面类型识别

逐页分析每个 PDF：

| 类型 | 判定条件 |
|------|----------|
| `text` | 可提取文本 ≥ 阈值（默认50字符） |
| `scanned` | 含图像且可提取文本 < 阈值 |
| `mixed` | 同页同时满足文字与图像特征 |
| `empty` | 既无有效文本也无图像 |

文档级类型取页面类型的多数投票；平局时取 `mixed`。

### 3. 文档长度分布

对可解析文档提取纯文本，统计字符数。输出：
- 分位数：P25、P50、P75、P90、P95
- 区间分布：可配置（默认5个区间）
- 每文件字符数列表（按路径）

支持格式：`.txt` `.md` `.pdf` `.docx` `.html` `.htm` `.json` `.csv` `.xml`

### 4. 重复检测

- **MD5 精确匹配**：对文件二进制内容计算 MD5，归组完全相同的文件
- **SimHash 近似匹配**：对文本内容计算 64 位 SimHash，汉明距离 ≤ 阈值视为近似重复
- **性能优化**：跳过文件大小差异超过3倍的文件对，大幅减少比较次数

### 5. 敏感信息检测

正则匹配以下模式，附带前后上下文：

| 类型 | 模式 |
|------|------|
| `phone` | 中国大陆手机号 `1[3-9]\d{9}` |
| `email` | 标准邮箱格式 |
| `id_card` | 15 位或 18 位身份证号 |

报告中对匹配值做部分脱敏（保留前 3 后 4 字符）。

### 6. 文档分类标签体系

根据以上分析结果，自动为每个文件打标签：

| 标签 | 触发条件 |
|------|----------|
| `Text_PDF` | PDF文字型 |
| `Scan_PDF` | PDF扫描型 |
| `Mixed_PDF` | PDF混合型 |
| `Needs_OCR` | 需要OCR处理 |
| `DOCX` | Word文档 |
| `Markdown` | Markdown文档 |
| `Short_Doc` | 极短文档(<500字) |
| `Long_Doc` | 超长文档(>5万字) |
| `Duplicate` | 存在完全重复 |
| `Sensitive` | 包含敏感信息 |
| `Unsupported` | 不支持的格式 |

## 配置文件

所有阈值均可通过 `assessment_config.yaml` 配置，无需修改代码。

```bash
# 使用自定义配置
python scripts/assess_documents.py --input ./docs --config my_config.yaml

# 命令行覆盖单个参数
python scripts/assess_documents.py --input ./docs --simhash-threshold 2
```

## 故障排除

| 问题 | 处理 |
|------|------|
| `ImportError: fitz` | `pip install pymupdf` |
| `ImportError: docx` | `pip install python-docx` |
| `ImportError: yaml` | `pip install pyyaml` |
| PDF 解析失败 | 记录到 `meta.errors`，跳过该文件继续 |
| 编码错误 | 文本文件 fallback 为 `utf-8` 忽略错误 |
| SimHash 比较太慢 | 调低 `simhash_threshold` 或增大 `size_ratio_skip` |

## 附加资源

- 配置文件：[assessment_config.yaml](assessment_config.yaml)
- 完整 JSON/HTML schema：[reference.md](reference.md)
