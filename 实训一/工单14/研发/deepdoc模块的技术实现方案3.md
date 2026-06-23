# DeepDoc 模块的技术实现方案 3 — 深度解析模块全面分析

> **分析范围**：DeepDoc 内置的所有文件解析器、支持的文件类型、PDF 解析技术深度剖析  
> **代码位置**：`ragflow-main/deepdoc/`  
> **文档生成时间**：2026年6月

---

## 目录

- [一、DeepDoc 模块架构总览](#一deepdoc-模块架构总览)
- [二、内置解析器清单与支持的文件类型](#二内置解析器清单与支持的文件类型)
  - [2.1 解析器总览表](#21-解析器总览表)
  - [2.2 文件类型 → 解析器映射](#22-文件类型--解析器映射)
- [三、PDF 解析技术深度剖析](#三pdf-解析技术深度剖析)
  - [3.1 RAGFlowPdfParser 核心架构](#31-ragflowpdfparser-核心架构)
  - [3.2 PDF 渲染与字符提取](#32-pdf-渲染与字符提取)
  - [3.3 OCR 文字检测与识别管线](#33-ocr-文字检测与识别管线)
  - [3.4 布局分析（Layout Recognition）](#34-布局分析layout-recognition)
  - [3.5 表格结构识别（Table Structure Recognition）](#35-表格结构识别table-structure-recognition)
  - [3.6 智能文本合并管线](#36-智能文本合并管线)
  - [3.7 表格与图表提取](#37-表格与图表提取)
  - [3.8 语言检测](#38-语言检测)
  - [3.9 位置标记系统](#39-位置标记系统)
  - [3.10 完整解析管线流程图](#310-完整解析管线流程图)
- [四、PDF 备选解析后端](#四pdf-备选解析后端)
  - [4.1 PlainParser（纯文本降级）](#41-plainparser纯文本降级)
  - [4.2 VisionParser（Vision LLM）](#42-visionparservision-llm)
  - [4.3 DoclingParser（IBM Docling）](#43-doclingparseribm-docling)
  - [4.4 MinerUParser（MinerU API）](#44-mineruparsermineru-api)
  - [4.5 PaddleOCRParser（PaddleOCR-VL API）](#45-paddleocrparserpaddleocr-vl-api)
  - [4.6 TCADPParser（腾讯云 LKEAP API）](#46-tcadpparser腾讯云-lkeap-api)
- [五、ONNX 模型与视觉识别模块](#五onnx-模型与视觉识别模块)
  - [5.1 四个核心 ONNX 模型](#51-四个核心-onnx-模型)
  - [5.2 OCR 模块（TextDetector + TextRecognizer）](#52-ocr-模块textdetector--textrecognizer)
  - [5.3 布局识别器（LayoutRecognizer）](#53-布局识别器layoutrecognizer)
  - [5.4 表格结构识别器（TableStructureRecognizer）](#54-表格结构识别器tablestructurerecognizer)
- [六、其他文件解析器详解](#六其他文件解析器详解)
  - [6.1 DOCX 解析器](#61-docx-解析器)
  - [6.2 Excel 解析器](#62-excel-解析器)
  - [6.3 HTML 解析器](#63-html-解析器)
  - [6.4 PPT 解析器](#64-ppt-解析器)
  - [6.5 TXT 解析器](#65-txt-解析器)
  - [6.6 JSON 解析器](#66-json-解析器)
  - [6.7 Markdown 解析器](#67-markdown-解析器)
  - [6.8 图表描述器（VisionFigureParser）](#68-图表描述器visionfigureparser)
  - [6.9 简历解析器（resume）](#69-简历解析器resume)
- [七、XGBoost 特征工程详解](#七xgboost-特征工程详解)

---

## 一、DeepDoc 模块架构总览

DeepDoc 是 RAGFlow 的深度文档理解模块，位于 `deepdoc/` 目录，包含**视觉识别**、**解析器**、**识别器**三大子系统：

```
┌──────────────────────────────────────────────────────────────────┐
│                      DeepDoc 模块架构                             │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  deepdoc/                                                        │
│  ├── parser/                    # 文件解析器层                    │
│  │   ├── pdf_parser.py          # ⭐ PDF 核心解析器（1509行）      │
│  │   │   ├── RAGFlowPdfParser   # 主解析器（OCR+布局+表格+合并）   │
│  │   │   ├── PlainParser        # 纯文本降级                     │
│  │   │   └── VisionParser       # Vision LLM 解析               │
│  │   ├── docx_parser.py         # Word 文档解析器                 │
│  │   ├── excel_parser.py        # Excel/CSV 解析器               │
│  │   ├── html_parser.py         # HTML 解析器                    │
│  │   ├── ppt_parser.py          # PowerPoint 解析器              │
│  │   ├── txt_parser.py          # 纯文本解析器                    │
│  │   ├── json_parser.py         # JSON/JSONL 解析器              │
│  │   ├── markdown_parser.py     # Markdown 解析器                │
│  │   ├── figure_parser.py       # Vision 图表描述器               │
│  │   ├── docling_parser.py      # IBM Docling 集成               │
│  │   ├── mineru_parser.py       # MinerU API 集成               │
│  │   ├── paddleocr_parser.py    # PaddleOCR-VL API 集成         │
│  │   ├── tcadp_parser.py        # 腾讯云 LKEAP API 集成          │
│  │   ├── resume/                # 简历解析子模块                  │
│  │   └── utils.py               # 工具函数                       │
│  │                                                          │
│  ├── vision/                      # 视觉识别层                  │
│  │   ├── ocr.py                  # OCR 引擎（751行）            │
│  │   │   ├── OCR                 # OCR 管线封装                  │
│  │   │   ├── TextDetector        # 文字检测（det.onnx）          │
│  │   │   ├── TextRecognizer      # 文字识别（rec.onnx）          │
│  │   │   └── load_model()        # ONNX 模型加载                │
│  │   ├── layout_recognizer.py    # 布局识别器（457行）           │
│  │   │   ├── LayoutRecognizer    # ONNX 布局分类                │
│  │   │   ├── LayoutRecognizer4YOLOv10  # YOLOv10 布局分类       │
│  │   │   └── AscendLayoutRecognizer    # 昇腾 NPU 布局分类      │
│  │   ├── table_structure_recognizer.py  # 表格结构识别（612行）   │
│  │   ├── recognizer.py           # 基础识别器类（442行）         │
│  │   ├── operators.py            # 图像预处理算子（733行）       │
│  │   ├── postprocess.py          # 后处理（DB/CTC）（370行）     │
│  │   └── seeit.py                # 可视化工具                    │
│  │                                                          │
│  └── res/deepdoc/                # ONNX 模型文件目录            │
│      ├── det.onnx                # 文字检测模型                  │
│      ├── rec.onnx                # 文字识别模型                  │
│      ├── layout.onnx             # 布局分类模型                  │
│      ├── tsr.onnx                # 表格结构识别模型              │
│      └── ocr.res                 # CTC 字符字典                 │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 二、内置解析器清单与支持的文件类型

### 2.1 解析器总览表

| 解析器文件 | 类名 | 支持文件类型 | 核心技术 | 代码行数 |
|-----------|------|------------|---------|---------|
| `pdf_parser.py` | **RAGFlowPdfParser** | PDF | OCR(ONNX) + 布局CNN + 表格结构 + XGBoost | **1509** |
| `pdf_parser.py` | PlainParser | PDF | pypdf 纯文本提取 | 33 |
| `pdf_parser.py` | VisionParser | PDF | Vision LLM 逐页描述 | 53 |
| `docx_parser.py` | RAGFlowDocxParser | .docx | python-docx + 表格智能分析 | 139 |
| `excel_parser.py` | RAGFlowExcelParser | .xlsx/.xls/.csv | openpyxl/pandas/calamine 多引擎 | 270 |
| `html_parser.py` | RAGFlowHtmlParser | .html/.htm | BeautifulSoup + 递归提取 | 213 |
| `ppt_parser.py` | RAGFlowPptParser | .pptx | python-pptx + 形状类型路由 | 96 |
| `txt_parser.py` | RAGFlowTxtParser | .txt/.log | 分隔符切分 + token 计数 | 64 |
| `json_parser.py` | RAGFlowJsonParser | .json/.jsonl | 递归结构感知切分 | 179 |
| `markdown_parser.py` | RAGFlowMarkdownParser | .md/.markdown | 正则表格/结构元素提取 | 321 |
| `figure_parser.py` | VisionFigureParser | 图片（增强层） | Vision LLM 图表描述 | 255 |
| `docling_parser.py` | DoclingParser | PDF | IBM Docling 库 | 356 |
| `mineru_parser.py` | MinerUParser | PDF | MinerU API（7种后端） | 673 |
| `paddleocr_parser.py` | PaddleOCRParser | PDF | PaddleOCR-VL API | 554 |
| `tcadp_parser.py` | TCADPParser | PDF | 腾讯云 LKEAP API | 547 |

### 2.2 文件类型 → 解析器映射

```
文件类型扩展名         使用的解析器
─────────────────────────────────────────
.pdf           →  RAGFlowPdfParser / PlainParser / VisionParser
                 / DoclingParser / MinerUParser / PaddleOCRParser / TCADPParser
.docx          →  RAGFlowDocxParser
.xlsx / .xls   →  RAGFlowExcelParser
.csv           →  RAGFlowExcelParser
.html / .htm   →  RAGFlowHtmlParser
.pptx          →  RAGFlowPptParser
.txt / .log    →  RAGFlowTxtParser
.json / .jsonl →  RAGFlowJsonParser
.md            →  RAGFlowMarkdownParser
.doc           →  Tika（外部依赖）
图片            →  VisionFigureParser（增强层，非独立解析）
简历            →  resume 模块（step_one + step_two）
```

---

## 三、PDF 解析技术深度剖析

### 3.1 RAGFlowPdfParser 核心架构

`RAGFlowPdfParser` 是 DeepDoc 最核心的解析器（**1509 行代码**），实现了完整的深度文档理解管线。

**类继承关系**：

```
RAGFlowPdfParser
    ├── DoclingParser     (docling_parser.py)  — IBM Docling 扩展
    ├── MinerUParser      (mineru_parser.py)   — MinerU API 扩展
    ├── PaddleOCRParser   (paddleocr_parser.py) — PaddleOCR-VL 扩展
    ├── TCADPParser       (tcadp_parser.py)     — 腾讯云 API 扩展
    └── VisionParser      (pdf_parser.py)       — Vision LLM 扩展
```

**初始化组件**：

```python
# deepdoc/parser/pdf_parser.py (lines 56-108)
class RAGFlowPdfParser:
    def __init__(self, **kwargs):
        # 1. OCR 引擎（基于 ONNX 的自定义 OCR，非 PaddleOCR 库）
        self.ocr = OCR()
        
        # 2. 布局识别器（ONNX 或 昇腾 NPU）
        if os.environ.get("LAYOUT_RECOGNIZER_TYPE", "onnx") == "ascend":
            self.layouter = AscendLayoutRecognizer("layout")
        else:
            self.layouter = LayoutRecognizer("layout")
        
        # 3. 表格结构识别器
        self.tbl_det = TableRecognizer("table_structure")
        
        # 4. XGBoost 文本合并决策模型
        self.updown_concat_model = xgboost.XGBClassifier()
        self.updown_concat_model.load_model(
            "rag/res/deepdoc/updown_concat_xgb.json"
        )
        
        # 5. 并行推理信号量
        if settings.PARALLEL_DEVICES > 1:
            self.parallel_limiters = [
                asyncio.Semaphore(1) for _ in range(settings.PARALLEL_DEVICES)
            ]
```

### 3.2 PDF 渲染与字符提取

**方法**：`__images__()`（第 1047-1185 行）

```python
def __images__(self, fnm, zoomin=3, page_from=0, page_to=299, callback=None):
    """
    PDF 渲染管线：
    1. 使用 pdfplumber 将 PDF 页面渲染为图像
    2. 提取每页的字符元数据（位置、大小、颜色）
    3. 使用 pypdf 提取书签/大纲
    4. 异步 OCR 处理所有页面
    """
```

**渲染参数**：

| 参数 | 值 | 说明 |
|------|-----|------|
| 渲染 DPI | 72 × zoomin（默认 3）= **216 DPI** | 平衡清晰度与性能 |
| zoomin | 3（默认），最大 27 | 缩放因子，不够清晰时自动递增 ×3 |
| 缩放后尺寸 | 原始尺寸 × zoomin | 用于坐标映射回原页面 |

**渲染流程**：

```python
# 使用 pdfplumber 渲染页面
with pdfplumber.open(io.BytesIO(binary)) as pdf:
    for i, page in enumerate(pdf.pages):
        # 1. 渲染页面为图像
        img = page.to_image(resolution=72 * zoomin)
        
        # 2. 提取字符元数据（去重）
        chars = page.dedupe_chars()
        # chars[i] = {
        #   "text": "A",
        #   "x0": 100.5, "top": 200.3,  # 位置坐标
        #   "size": 12.0,                # 字体大小
        #   "non_stroking_color": (0,0,0) # 颜色
        # }
        
        # 3. 过滤彩色字符（保留灰度/黑色）
        chars = [c for c in chars if not self._has_color(c)]
```

**字符预处理**：

```python
# 在字母数字之间插入空格（基于间距判断）
for i in range(len(chars) - 1):
    if (is_alnum(chars[i]["text"]) and is_alnum(chars[i+1]["text"])
        and chars[i+1]["x0"] - chars[i]["x1"] > avg_width * 0.3):
        chars[i]["text"] += " "  # 插入空格
```

**关键设计**：

- 如果 zoomin=3 时未检测到任何文本框，**自动递增 zoomin ×3 重试**（最大 zoomin=27）
- 支持**异步 OCR**：所有页面通过 `asyncio.gather` 并行处理
- 多 GPU 支持：通过 `PARALLEL_DEVICES` 和信号量控制并行推理

### 3.3 OCR 文字检测与识别管线

**方法**：`__ocr()`（第 285-348 行）

**技术架构**：

> **重要发现**：DeepDoc 的 OCR **不是直接使用 PaddleOCR 库**，而是使用 PaddleOCR 导出的 ONNX 模型，通过 ONNX Runtime 推理。本质上是**自定义实现的 PaddleOCR 管线**。

**OCR 管线流程**：

```
┌──────────────────────────────────────────────────────────────┐
│              DeepDoc OCR 管线（3 阶段）                       │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Stage 1: 文字检测（TextDetector）                            │
│  ├── 模型: det.onnx (DB 文字检测)                             │
│  ├── 输入: 页面图像 (numpy array)                             │
│  ├── 输出: 文字区域边界框列表                                  │
│  └── 后处理: DBPostProcess（轮廓查找 + 膨胀 + 评分）          │
│                                                              │
│  Stage 2: 字符合并                                           │
│  ├── 将 pdfplumber 提取的字符合并到检测框中                    │
│  ├── 匹配条件: 框高度与字符高度差异 < 30%                      │
│  └── 效果: 结合 pdfplumber 精确位置 + OCR 检测区域            │
│                                                              │
│  Stage 3: 文字识别（TextRecognizer）                          │
│  ├── 模型: rec.onnx (CTC 文字识别)                            │
│  ├── 仅对无文本的框执行（pdfplumber 已有文本的跳过）           │
│  ├── 输入: 裁剪后的文字区域图像                               │
│  ├── 输出: 识别文本 + 置信度                                  │
│  └── 过滤: drop_score < 0.5 的结果丢弃                       │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

**`__ocr()` 核心代码**：

```python
def __ocr(self, pagenum, img, chars, ZM=3, device_id=None):
    """
    Stage 1: 文字检测
    """
    # PaddleOCR 检测文字区域
    boxes, _ = self.ocr.detect(np.array(img))
    # boxes = [[x0,y0], [x1,y0], [x1,y1], [x0,y1]]  # 四个角坐标
    
    # 按 Y 位置排序
    boxes = sorted(boxes, key=lambda x: (x[0][0][1] + x[0][2][1]) / 2)
    
    """
    Stage 2: 字符合并（pdfplumber + OCR 融合）
    """
    for i, b in enumerate(boxes):
        # 将 pdfplumber 提取的字符合并到 OCR 检测框中
        for c in chars:
            if (abs(c["top"] - b[0][0][1]) < avg_height * 0.3  # 高度匹配
                and b[0][0][0] <= c["x0"] <= b[0][2][0]):       # X 范围内
                boxes[i]["text"] += c["text"]
    
    """
    Stage 3: 文字识别（仅对无文本的框）
    """
    for i, b in enumerate(boxes):
        if not b.get("text"):  # pdfplumber 未提取到文本
            # 透视变换裁剪文字区域
            crop_img = self.ocr.get_rotate_crop_image(np.array(img), b)
            # CTC 文字识别
            text, score = self.ocr.recognize_batch([crop_img])
            if score >= 0.5:  # 置信度过滤
                b["text"] = text
```

**OCR 初始化**（`deepdoc/vision/ocr.py`）：

```python
class OCR:
    def __init__(self):
        # 文字检测模型（DB 算法）
        self.detector = TextDetector()  # 加载 det.onnx
        
        # 文字识别模型（CTC 算法）
        self.recognizer = TextRecognizer()  # 加载 rec.onnx
    
    def detect(self, img):
        """文字检测：输入图像 → 输出文字区域边界框"""
        det_res = self.detector(img)
        return det_res
    
    def recognize_batch(self, imgs):
        """批量文字识别：输入裁剪图像列表 → 输出文本+置信度"""
        return self.recognizer(imgs)
```

### 3.4 布局分析（Layout Recognition）

**方法**：`_layouts_rec()`（第 350-356 行）

**三种布局识别器实现**：

| 实现 | 模型文件 | 硬件 | 切换方式 |
|------|---------|------|---------|
| `LayoutRecognizer` | `layout.onnx` | CPU/GPU（ONNX Runtime） | 默认 |
| `LayoutRecognizer4YOLOv10` | `layout.onnx` | CPU/GPU（YOLOv10 推理） | 默认（实际使用） |
| `AscendLayoutRecognizer` | `layout.om` | 昇腾 NPU | `LAYOUT_RECOGNIZER_TYPE=ascend` |

**布局分类标签**：

| 标签 | 说明 | 对后续处理的影响 |
|------|------|----------------|
| `title` | 标题 | 标记为文档结构锚点 |
| `text` | 正文文本 | 参与文本合并 |
| `figure` | 图片/图表 | 提取为独立元素 |
| `figure caption` | 图片标题 | 关联到最近的 figure |
| `table` | 表格 | 触发表格结构识别 |
| `table caption` | 表格标题 | 关联到最近的 table |
| `reference` | 参考文献 | 可过滤的"垃圾布局" |
| `header` | 页眉 | 可过滤的"垃圾布局" |
| `footer` | 页脚 | 可过滤的"垃圾布局" |
| `equation` | 公式 | 保留为独立元素 |

**布局识别流程**：

```python
def _layouts_rec(self, ZM, drop=True):
    """
    布局分析：为每个 OCR 文字框打上布局类型标签
    
    输入: self.boxes（OCR 检测的文字框列表）
    输出: 每个 box 增加 "layoutno" 字段（布局类型标签）
    """
    # 调用 ONNX/YOLO 布局识别模型
    self.layouter(self.page_images, self.boxes, ZM, drop=drop)
    
    # 添加累计页高度（跨页定位用）
    for i, b in enumerate(self.boxes):
        b["top"] += cum_height[b["page"]]
        b["bottom"] += cum_height[b["page"]]
```

**垃圾布局清理**：

```python
# LayoutRecognizer 内部自动清理
# 移除: footer, header, reference 等重复的非内容布局
# 去重: 识别重复出现的页眉/页脚文本并移除
```

### 3.5 表格结构识别（Table Structure Recognition）

**方法**：`_table_transformer_job()`（第 199-283 行）

**识别模型**：`tsr.onnx`（Table Structure Recognizer）

**表格组件标签**：

| 标签 | 缩写 | 说明 |
|------|------|------|
| `table row` | R | 表格行 |
| `table column header` | H | 表头列 |
| `table column` | C | 表格列 |
| `table spanning cell` | SP | 合并单元格 |
| `table projected row header` | — | 投影行头 |
| `table` | — | 整个表格区域 |

**识别流程**：

```python
def _table_transformer_job(self, ZM):
    """
    表格结构识别管线
    """
    # Step 1: 从页面图像中裁剪表格区域
    for layout_box in table_layouts:
        # 裁剪表格图像（加 MARGIN=10px 边距）
        img = crop_image(page_img, layout_box, margin=10)
        imgs.append(img)
    
    # Step 2: 运行表格结构识别模型
    tbl_res = self.tbl_det(imgs)
    # tbl_res = [
    #   {"type": "table row", "bbox": [[x0,y0],[x1,y0],[x1,y1],[x0,y1]]},
    #   {"type": "table column header", "bbox": [...]},
    #   ...
    # ]
    
    # Step 3: 将表格组件标签分配到 OCR 文字框
    for box in self.boxes:
        if box 在某个 table row 内:
            box["tag"] = "R"  # 行标记
        if box 在某个 table column header 内:
            box["tag"] = "H"  # 表头标记
        if box 在某个 table column 内:
            box["tag"] = "C"  # 列标记
        if box 在某个 spanning cell 内:
            box["tag"] = "SP" # 合并单元格标记
```

**表格构造**（`TableStructureRecognizer.construct_table()`）：

```python
@staticmethod
def construct_table(tbl_res, ocr_boxes):
    """
    从识别结果构建 HTML 表格
    
    流程：
    1. 按行（R）分组文字框
    2. 按列（C）排序
    3. 识别表头（H）和合并单元格（SP）
    4. 生成 HTML <table> 结构
    """
    # 构建 HTML
    html = "<table>"
    for row in rows:
        html += "<tr>"
        for cell in row:
            if cell.is_header:
                html += f"<th>{cell.text}</th>"
            else:
                html += f"<td>{cell.text}</td>"
        html += "</tr>"
    html += "</table>"
    return html
```

### 3.6 智能文本合并管线

这是 RAGFlowPdfParser 最核心的创新，分为五个阶段：

```
┌──────────────────────────────────────────────────────────────┐
│              智能文本合并管线（5 阶段）                        │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Stage 1: 水平合并 (_text_merge)                              │
│  ├── 先执行列检测 (_assign_column)                            │
│  ├── 同页、同列、同版面内的相邻文本框水平合并                   │
│  └── 合并条件: Y 距离 < 平均高度/3                            │
│                                                              │
│  Stage 2: 列检测 (_assign_column)                             │
│  ├── KMeans 聚类检测 1-4 列布局                               │
│  ├── 轮廓系数（Silhouette Score）选最优 k                     │
│  └── 全局列数通过多数投票确定                                 │
│                                                              │
│  Stage 3: 垂直合并 (_concat_downward / _naive_vertical_merge) │
│  ├── XGBoost 31 维特征决策（当前为死代码，实际用朴素合并）     │
│  ├── 朴素合并: 基于标点、版面、间距的规则                      │
│  └── 输出: 连贯的文本段落                                     │
│                                                              │
│  Stage 4: 垂直排序 (_final_reading_order_merge)               │
│  ├── 按列分组 → 组内按 Y/X 排序                               │
│  └── 确定最终阅读顺序                                         │
│                                                              │
│  Stage 5: 文本清理 (__filterout_scraps)                       │
│  ├── DFS 分组过滤低质量文本                                   │
│  ├── 保留: 布局型文本、宽文本(>1/3页宽)、高文本(>平均高)       │
│  └── 生成最终输出文本                                         │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

#### Stage 2 详解：列检测（KMeans 聚类）

```python
def _assign_column(boxes, zoomin=3):
    """
    KMeans 聚类检测文档列布局
    
    算法：
    1. 收集每页所有文字框的 x0（左边界）坐标
    2. 尝试 k=1 到 min(4, 文字框数) 的聚类
    3. 用轮廓系数（Silhouette Score）选择最优 k
    4. 全局列数通过各页的多数投票确定
    5. 按全局 k 重新聚类，分配 col_id
    """
    page_x0s = defaultdict(list)
    for b in boxes:
        page_x0s[b["page"]].append(b["x0"])
    
    # 各页独立确定最优 k
    k_choices = []
    for page, x0s in page_x0s.items():
        if len(x0s) < 2:
            k_choices.append(1)
            continue
        best_k, best_score = 1, -1
        for k in range(2, min(4, len(x0s)) + 1):
            kmeans = KMeans(n_clusters=k)
            labels = kmeans.fit_predict(np.array(x0s).reshape(-1, 1))
            score = silhouette_score(np.array(x0s).reshape(-1, 1), labels)
            if score > best_score:
                best_k, best_score = k, score
        k_choices.append(best_k)
    
    # 全局列数 = 多数投票
    global_k = Counter(k_choices).most_common(1)[0][0]
    
    # 按全局 k 重新聚类，分配 col_id
    kmeans = KMeans(n_clusters=global_k)
    for b in boxes:
        b["col_id"] = kmeans.predict([[b["x0"]]])[0]
```

#### Stage 3 详解：垂直合并

**当前实际执行的朴素合并**（`_naive_vertical_merge`）：

```python
def _naive_vertical_merge(self, zoomin=3):
    """
    基于规则的垂直文本合并
    
    合并条件（concatting）：
    - 上方文本以逗号/标点结尾
    - 下方文本以句号/问号开头
    - 同一版面类型
    
    分离条件（detaching）：
    - 不同版面类型
    - 上方文本以句号结尾（英文句号）
    - 间距过大（> 平均高度 × 1.5）
    - 跨页 X 坐标不对齐
    """
```

**XGBoost 模型（当前为死代码）**：

> **重要发现**：`_concat_downward()` 方法在第 588 行有一个 `return` 语句，导致后续的 XGBoost 31 维特征推理代码**永远不会执行**。当前实际使用的是 `_naive_vertical_merge()` 的朴素规则合并。

XGBoost 模型仍被加载（`updown_concat_xgb.json`），但其推理代码已被跳过。

### 3.7 表格与图表提取

**方法**：`_extract_table_figure()`（第 762-935 行）

```python
def _extract_table_figure(self, need_image, ZM, return_html, need_position):
    """
    表格与图表提取管线
    """
    # 1. 从 self.boxes 中提取表格和图表区域
    tbls = [b for b in self.boxes if b.get("layoutno") in ["table", "figure"]]
    
    # 2. 跨页表格合并（相邻页、距离 < 23×平均高度）
    for tbl in tbls:
        if tbl["page"] - prev_tbl["page"] <= 1:
            if tbl["top"] - prev_tbl["bottom"] < 23 * mean_height:
                # 合并跨页表格
                merge_tables(prev_tbl, tbl)
    
    # 3. 标题关联（欧氏距离匹配最近的表格/图表）
    for cap in captions:
        nearest = find_nearest(tbls, cap, metric="euclidean")
        cap["associated_to"] = nearest["id"]
    
    # 4. 图像裁剪
    def cropout(box):
        # 从页面图像裁剪区域
        img = page_img.crop((x0, top, x1, bottom))
        return img
    
    # 5. 返回 (图像, 文本/HTML) 对列表
    return [(image, text_or_html), ...]
```

### 3.8 语言检测

```python
# deepdoc/parser/pdf_parser.py (lines 1047-1185 中)
def __images__(self, fnm, zoomin=3, ...):
    # ...
    
    """
    启发式语言检测
    采样每页 100 个随机字符 → 检查是否存在 30+ 连续 ASCII 字符
    如果 >50% 页面检测为英文 → 设置 self.is_english = True
    """
    self.is_english = False
    english_pages = 0
    for page_chars in all_chars:
        sample = random.sample(page_chars, min(100, len(page_chars)))
        english_count = 0
        for c in sample:
            if re.match(r'[a-zA-Z0-9\s]', c["text"]):
                english_count += 1
        if english_count > 30:
            english_pages += 1
    
    if english_pages > len(all_chars) * 0.5:
        self.is_english = True
```

**语言检测影响**：
- `is_english=True`：OCR 和文本合并策略会调整（如句号判定、分词方式）
- 影响 `paper.chunk()` 中的摘要提取逻辑

### 3.9 位置标记系统

**方法**：`_line_tag()`（第 961-974 行）

```python
def _line_tag(self, bx, ZM):
    """
    生成位置标记字符串
    
    格式: @@page_num\tx0\tx1\ttop\tbottom##
    
    示例: @@3\t100.5\t500.2\t200.0\t250.5##
    含义: 第3页, x0=100.5, x1=500.2, top=200.0, bottom=250.5
    """
    return f"@@{bx['page']}\t{bx['x0']/ZM}\t{bx['x1']/ZM}\t{bx['top']/ZM}\t{bx['bottom']/ZM}##"
```

**位置标记用途**：
1. **图像裁剪**：`crop()` 方法根据位置标记从页面图像裁剪对应区域
2. **精确回溯**：在检索结果中定位到 PDF 原始页面的具体位置
3. **跨页追踪**：支持跨页的文本和图像定位

**`crop()` 方法**（第 1294-1403 行）：

```python
def crop(self, text, ZM=3, need_position=False):
    """
    根据位置标记裁剪页面图像
    
    流程：
    1. 解析 text 中的 @@...## 位置标记
    2. 从对应页面图像裁剪区域
    3. 添加 120px 上下文边距
    4. 首尾段添加 50% 透明遮罩
    5. 拼接为合成图像
    """
```

### 3.10 完整解析管线流程图

```
┌──────────────────────────────────────────────────────────────────────┐
│            RAGFlowPdfParser.__call__() 完整解析管线                   │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  输入: PDF 文件 (filename + binary)                                   │
│                                                                      │
│  ① __images__() ─── PDF 渲染 + 字符提取 + OCR                        │
│  │   ├── pdfplumber 渲染 → 216 DPI 图像                               │
│  │   ├── 提取字符元数据 (位置/大小/颜色)                               │
│  │   ├── pypdf 提取书签                                               │
│  │   ├── 语言检测 (英文/中文)                                          │
│  │   └── 异步 OCR (文字检测 + 文字识别)                                │
│  │                                                                    │
│  ② _layouts_rec() ─── 布局分析                                       │
│  │   ├── ONNX/YOLO 模型推理                                           │
│  │   └── 每个文字框打上: title/text/table/figure/... 标签              │
│  │                                                                    │
│  ③ _table_transformer_job() ─── 表格结构识别                          │
│  │   ├── 裁剪表格区域图像                                             │
│  │   ├── TSR 模型推理 → 识别行(R)/列(C)/表头(H)/合并(SP)              │
│  │   └── 为表格内文字框打上标签                                        │
│  │                                                                    │
│  ④ _text_merge() ─── 水平文本合并                                     │
│  │   ├── _assign_column() → KMeans 列检测                             │
│  │   └── 同列相邻框水平合并                                           │
│  │                                                                    │
│  ⑤ _concat_downward() ─── 垂直文本合并                                │
│  │   └── _naive_vertical_merge() → 基于规则的垂直合并                 │
│  │                                                                    │
│  ⑥ _filter_forpages() ─── 目录页过滤                                 │
│  │   └── 检测并移除 "目录" / "..." 模式页面                           │
│  │                                                                    │
│  ⑦ _extract_table_figure() ─── 表格/图表提取                         │
│  │   ├── 跨页表格合并                                                 │
│  │   ├── 标题关联 (欧氏距离)                                          │
│  │   └── 图像裁剪                                                     │
│  │                                                                    │
│  ⑧ __filterout_scraps() ─── 文本清理                                  │
│  │   ├── DFS 分组过滤低质量文本                                       │
│  │   └── 生成最终输出文本 + 位置标记                                   │
│  │                                                                    │
│  输出: (text, tables)                                                 │
│  ├── text: 带位置标记的全文本字符串                                   │
│  └── tables: 表格/图表列表 [(image, html/text), ...]                  │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 四、PDF 备选解析后端

### 4.1 PlainParser（纯文本降级）

```python
# deepdoc/parser/pdf_parser.py (lines 1419-1451)
class PlainParser:
    """
    最简单的 PDF 文本提取，不使用 OCR
    基于 pypdf 库的纯文本提取
    """
    def __call__(self, fnm, binary=None):
        # 1. 使用 pypdf 提取文本
        pdf = PdfReader(io.BytesIO(binary))
        txts = []
        for page in pdf.pages:
            txt = page.extract_text()
            if txt:
                txts.append((txt, ""))
        return txts, []
```

| 特性 | 说明 |
|------|------|
| 适用场景 | 文本型 PDF（非扫描件、嵌入文字） |
| 优点 | 速度最快，无需 GPU |
| 缺点 | 无法处理图片型 PDF、复杂版面 |
| OCR | ❌ 不支持 |
| 布局分析 | ❌ 不支持 |

### 4.2 VisionParser（Vision LLM）

```python
# deepdoc/parser/pdf_parser.py (lines 1453-1505)
class VisionParser(RAGFlowPdfParser):
    """
    使用 Vision LLM 进行 PDF 解析
    将每页渲染为图像 → 发送给 Vision LLM → 获取文本描述
    """
    def __call__(self, fnm, need_image=True, zoomin=3, return_html=False):
        # 1. 仅渲染页面图像（不执行 OCR）
        self.__images__(fnm, zoomin, page_from, page_to, callback)
        
        # 2. 逐页发送给 Vision LLM
        for i, img in enumerate(self.page_images):
            txt = vision_llm_chunk(self.vision_llm, img)
            # 生成全页位置标记
            text = f"@@{i}\t0\t{img.width}\t0\t{img.height}##\n{txt}"
            txts.append((text, ""))
        
        return txts, []
```

| 特性 | 说明 |
|------|------|
| 适用场景 | 极复杂版面、需要语义理解 |
| 优点 | 版面理解能力最强 |
| 缺点 | 速度慢、成本高（需要 LLM API） |
| 依赖 | 需要配置 Image2Text 模型 |

### 4.3 DoclingParser（IBM Docling）

```python
# deepdoc/parser/docling_parser.py
class DoclingParser(RAGFlowPdfParser):
    """
    封装 IBM Docling 文档转换库
    继承自 RAGFlowPdfParser，fallback 到基类
    """
    def parse_pdf(self, filepath, binary, callback, *, output_dir, lang, method, ...):
        # 1. 使用 Docling DocumentConverter 转换 PDF
        converter = DocumentConverter()
        result = converter.convert(source)
        doc = result.document
        
        # 2. 提取文本块（含标题层级 + 边界框）
        sections = self._transfer_to_sections(doc, parse_method)
        
        # 3. 导出表格为 HTML
        tables = self._transfer_to_tables(doc)
        
        return sections, tables
```

| 特性 | 说明 |
|------|------|
| 适用场景 | 结构化文档 |
| 优点 | IBM 企业级文档理解 |
| 缺点 | 需要 `USE_DOCLING=true` 启用 |
| 依赖 | `docling` Python 包 |

### 4.4 MinerUParser（MinerU API）

```python
# deepdoc/parser/mineru_parser.py
class MinerUParser(RAGFlowPdfParser):
    """
    封装 MinerU API，支持 7 种后端
    """
    BACKENDS = [
        "pipeline",          # 纯管线模式
        "vlm-transformers",  # VLM + Transformers
        "vlm-vllm",          # VLM + vLLM 推理
        "vlm-mlx",           # VLM + MLX（Apple Silicon）
        "vlm-lmdeploy",      # VLM + LMDeploy
        "vlm-http-client",   # VLM HTTP 客户端
    ]
```

| 特性 | 说明 |
|------|------|
| 支持语言 | 18 种（中/英/日/韩/法/德/俄/阿/印/泰/越/意/葡/西/荷/土/波/捷/瑞典） |
| 输出格式 | `content_list.json`（含类型化块） |
| 块类型 | text, table, equation, code, list, image, discarded |
| 功能开关 | 公式识别、表格识别可独立开关 |
| 安全 | ZIP 解压时路径穿越保护 |

### 4.5 PaddleOCRParser（PaddleOCR-VL API）

```python
# deepdoc/parser/paddleocr_parser.py
class PaddleOCRParser(RAGFlowPdfParser):
    """
    远程 PaddleOCR-VL API 集成
    VLM（视觉语言模型）解析
    """
    def parse_pdf(self, filepath, binary, callback, *, parse_method, ...):
        # 1. 构建 API 请求（Base64 编码文件）
        payload = self._build_payload(data, "pdf", config)
        
        # 2. 发送 POST 请求
        result = self._send_request(payload, config, callback)
        
        # 3. 解析 Markdown 输出
        sections = self._transfer_to_sections(result, algorithm, parse_method)
        
        return sections, tables
```

| 可配置参数 | 说明 |
|-----------|------|
| `layout_detection` | 布局检测开关 |
| `chart_recognition` | 图表识别开关 |
| `seal_recognition` | 印章识别开关 |
| `formula_recognition` | 公式识别开关 |
| `polygon_points` | 多边形点位 |

### 4.6 TCADPParser（腾讯云 LKEAP API）

```python
# deepdoc/parser/tcadp_parser.py
class TCADPParser(RAGFlowPdfParser):
    """
    腾讯云 LKEAP 文档智能解析 API
    SSE（Server-Sent Events）流式响应
    """
    def parse_pdf(self, filepath, binary, callback, *, output_dir, file_type, ...):
        # 1. 调用腾讯云 SDK
        client = TencentCloudAPIClient()
        result = client.reconstruct_document(file_bytes)
        
        # 2. SSE 流式接收结果
        # 3. 下载 ZIP 结果包
        # 4. 解析 JSON + Markdown 内容
        sections = self._parse_content_to_sections(content_data)
        tables = self._parse_content_to_tables(content_data)
        
        return sections, tables
```

| 特性 | 说明 |
|------|------|
| 响应方式 | SSE 流式 + 指数退避重试 |
| 内容分类 | text, paragraph, table, image, equation |
| 输出格式 | JSON + Markdown（ZIP 包下载） |
| 安全 | ZIP 路径校验防止穿越攻击 |

---

## 五、ONNX 模型与视觉识别模块

### 5.1 四个核心 ONNX 模型

**模型存储路径**：`rag/res/deepdoc/`（首次运行时从 HuggingFace `InfiniFlow/deepdoc` 下载）

| 模型文件 | 任务名称 | 使用者 | 输入尺寸 | 算法 |
|---------|---------|--------|---------|------|
| `det.onnx` | 文字检测 | TextDetector | 动态 | DB（Differentiable Binarization） |
| `rec.onnx` | 文字识别 | TextRecognizer | 3×48×320 | CTC（Connectionist Temporal Classification） |
| `layout.onnx` | 布局分类 | LayoutRecognizer4YOLOv10 | 640×640 | YOLOv10 |
| `tsr.onnx` | 表格结构 | TableStructureRecognizer | 动态 | TableTransformer |

**支持文件**：

| 文件 | 说明 |
|------|------|
| `ocr.res` | CTC 解码字符字典 |
| `updown_concat_xgb.json` | XGBoost 文本合并模型（当前未使用） |
| `layout.om` | 昇腾 NPU 布局模型 |
| `tsr.om` | 昇腾 NPU 表格结构模型 |

### 5.2 OCR 模块（TextDetector + TextRecognizer）

**文件**：`deepdoc/vision/ocr.py`（751 行）

```python
class OCR:
    """自定义 OCR 引擎（基于 ONNX Runtime，非 PaddleOCR 库）"""
    
    def __init__(self):
        self.detector = TextDetector()    # det.onnx
        self.recognizer = TextRecognizer()  # rec.onnx

class TextDetector:
    """DB 文字检测"""
    def __call__(self, img):
        # 1. 预处理: DetResizeForTest → NormalizeImage → ToCHWImage
        # 2. ONNX 推理
        # 3. 后处理: DBPostProcess（轮廓查找 + 膨胀 + 评分）
        # 输出: 检测到的文字区域边界框列表

class TextRecognizer:
    """CTC 文字识别"""
    def __call__(self, imgs):
        # 1. 预处理: 归一化到 [-1, 1]
        # 2. ONNX 推理 (batch)
        # 3. CTC 解码: CTCLabelDecode
        # 输出: (文本列表, 置信度列表)
```

**ONNX 模型加载**（`load_model()` 函数）：

```python
def load_model(model_dir, nm, device_id):
    """
    加载 ONNX 模型
    
    特性：
    - 支持 GPU (CUDAExecutionProvider) 和 CPU (CPUExecutionProvider)
    - 模型缓存：loaded_models 字典，避免重复加载
    - GPU 显存可通过环境变量配置
    """
    model_path = model_dir / f"{nm}.onnx"
    
    providers = []
    if torch.cuda.is_available():
        providers.append(("CUDAExecutionProvider", {
            "gpu_mem_limit": int(os.environ.get("OCR_GPU_MEM_LIMIT_MB", 2048)) * 1024 * 1024,
        }))
    providers.append("CPUExecutionProvider")
    
    session = ort.InferenceSession(model_path, providers=providers)
    loaded_models[(str(model_path), device_id)] = session
    return session
```

### 5.3 布局识别器（LayoutRecognizer）

**文件**：`deepdoc/vision/layout_recognizer.py`（457 行）

**三种实现**：

| 类名 | 模型 | 硬件 | 特点 |
|------|------|------|------|
| `LayoutRecognizer` | layout.onnx | CPU/GPU | 基础 ONNX 推理 |
| `LayoutRecognizer4YOLOv10` | layout.onnx | CPU/GPU | YOLOv10 NMS 后处理（**实际使用**） |
| `AscendLayoutRecognizer` | layout.om | 昇腾 NPU | ais_bench 推理 |

**YOLOv10 后处理**（实际使用的实现）：

```python
class LayoutRecognizer4YOLOv10(LayoutRecognizer):
    def postprocess(self, input, img_size):
        """
        YOLOv10 专有后处理：
        1. xywh → xyxy 坐标转换
        2. 类别无关 NMS（IoU 阈值 0.45）
        3. 置信度阈值: 0.08
        """
        boxes = xywh2xyxy(input[:, :4])  # 中心点+宽高 → 左上+右下
        scores = input[:, 4]
        labels = input[:, 5].astype(int)
        
        # NMS 去重
        keep = nms(boxes, scores, iou_threshold=0.45)
        return boxes[keep], scores[keep], labels[keep]
```

**布局分类标签映射**：

```python
# LayoutRecognizer4YOLOv10 的标签
LABELS = [
    "title",           # 0
    "Text",            # 1
    "Reference",       # 2
    "Figure",          # 3
    "Figure caption",  # 4
    "Table",           # 5
    "Table caption",   # 6
    "Table caption",   # 7 (重复)
    "Equation",        # 8
    "Figure caption",  # 9 (重复)
]
```

### 5.4 表格结构识别器（TableStructureRecognizer）

**文件**：`deepdoc/vision/table_structure_recognizer.py`（612 行）

```python
class TableStructureRecognizer(Recognizer):
    """
    表格结构识别器
    
    标签: table, table column, table row, 
          table column header, table projected row header, table spanning cell
    """
    
    LABELS = [
        "table",
        "table column",
        "table row",
        "table column header",
        "table projected row header",
        "table spanning cell",
    ]
    
    @staticmethod
    def construct_table(tbl_res, ocr_boxes):
        """
        从识别结果构建 HTML 表格
        
        流程:
        1. 按行 (table row) 分组 OCR 框
        2. 按列 (table column) 排序
        3. 识别表头 (table column header)
        4. 检测合并单元格 (table spanning cell)
        5. 生成 HTML <table> 结构
        """
```

---

## 六、其他文件解析器详解

### 6.1 DOCX 解析器

**文件**：`deepdoc/parser/docx_parser.py`（139 行）

| 特性 | 说明 |
|------|------|
| 类名 | `RAGFlowDocxParser` |
| 依赖库 | `python-docx` |
| 支持格式 | .docx |

**核心能力**：
- 段落提取 + 样式名称（标题检测）
- 分页检测：通过 `lastRenderedPageBreak` XML 元素
- 表格提取：分类单元格内容类型（Date/Number/Currency/English 等）
- 智能表转文本：识别表头行 vs 数据行，输出 `field:value` 键值对

### 6.2 Excel 解析器

**文件**：`deepdoc/parser/excel_parser.py`（270 行）

| 特性 | 说明 |
|------|------|
| 类名 | `RAGFlowExcelParser` |
| 依赖库 | openpyxl / pandas / calamine（多引擎） |
| 支持格式 | .xlsx / .xls / .csv / .txt（制表符分隔） |

**多引擎加载链**：

```
尝试 1: openpyxl（原生 Excel 支持）
    ↓ 失败
尝试 2: pandas 默认引擎
    ↓ 失败
尝试 3: pandas calamine 引擎（Rust 实现，最快）
    ↓ 失败
尝试 4: CSV 自动检测 → 转换为 Workbook
```

**三种输出模式**：
- `__call__()`：`field: value` 键值对文本
- `html()`：HTML `<table>` 格式
- `markdown()`：Markdown 表格格式

### 6.3 HTML 解析器

**文件**：`deepdoc/parser/html_parser.py`（213 行）

| 特性 | 说明 |
|------|------|
| 类名 | `RAGFlowHtmlParser` |
| 依赖库 | BeautifulSoup + html5lib |
| 支持格式 | .html / .htm |

**核心能力**：
- 递归 DOM 遍历，尊重块级标签（h1-h6, p, div, ul, ol, table, pre, code）
- 标题标签 → Markdown 前缀（#, ##, ...）
- 大表格按 token 数分片
- Token 感知的分块

### 6.4 PPT 解析器

**文件**：`deepdoc/parser/ppt_parser.py`（96 行）

| 特性 | 说明 |
|------|------|
| 类名 | `RAGFlowPptParser` |
| 依赖库 | python-pptx |
| 支持格式 | .pptx |

**核心能力**：
- 形状类型感知：文本框 / 表格(shape_type=19) / 组合形状(shape_type=6)
- XPath 检测项目符号（`buChar` / `buAutoNum` / `buBlip`）
- 按位置排序（top//10 → left）确定阅读顺序

### 6.5 TXT 解析器

**文件**：`deepdoc/parser/txt_parser.py`（64 行）

| 特性 | 说明 |
|------|------|
| 类名 | `RAGFlowTxtParser` |
| 依赖库 | 无（纯 Python） |
| 支持格式 | .txt / .log |

**核心能力**：
- 可配置分隔符（默认：`\n!?;。；！？`）
- Unicode 转义处理
- Token 计数分块

### 6.6 JSON 解析器

**文件**：`deepdoc/parser/json_parser.py`（179 行）

| 特性 | 说明 |
|------|------|
| 类名 | `RAGFlowJsonParser` |
| 依赖库 | 无（纯 Python） |
| 支持格式 | .json / .jsonl |

**核心能力**：
- JSONL 自动检测（采样前 10 行，80% 有效即判定为 JSONL）
- 递归结构保持切分（保留嵌套字典结构）
- 可配置 max_chunk_size（默认 4000）和 min_chunk_size（默认 1800）

### 6.7 Markdown 解析器

**文件**：`deepdoc/parser/markdown_parser.py`（321 行）

| 特性 | 说明 |
|------|------|
| 类名 | `RAGFlowMarkdownParser` + `MarkdownElementExtractor` |
| 依赖库 | `markdown`（Markdown→HTML 渲染） |
| 支持格式 | .md / .markdown |

**核心能力**：
- 三种表格提取：有边框 Markdown 表格 / 无边框表格 / HTML 表格
- 结构元素提取：标题 / 代码块 / 列表 / 引用块 / 文本块
- 元数据支持（行号等）

### 6.8 图表描述器（VisionFigureParser）

**文件**：`deepdoc/parser/figure_parser.py`（255 行）

| 特性 | 说明 |
|------|------|
| 类名 | `VisionFigureParser` |
| 依赖库 | Vision LLM（IMAGE2TEXT 模型） |
| 适用范围 | 图片增强层（非独立解析器） |

**核心能力**：
- 将文档中的图片发送给 Vision LLM 生成描述
- 上下文感知提示（可包含图片周围的文本上下文）
- 10 线程并行处理，30 秒超时/图，3 次重试
- 三种包装器：DOCX / Excel / PDF 图片增强

### 6.9 简历解析器（resume）

**目录**：`deepdoc/parser/resume/`

| 文件 | 功能 |
|------|------|
| `step_one.py` | 简历字段定义（71 个字段）+ 数据清洗 |
| `step_two.py` | 教育分析 + 工作分析 + 项目分析 + 年龄计算 |
| `entities/` | 实体数据（企业/学历/行业/地区/学校） |

**解析能力**：
- 学校排名检测（985/211）
- 学历层级标准化
- 工作经历分析（公司规模/行业/岗位时长）
- 性别/年龄推断

---

## 七、XGBoost 特征工程详解

**方法**：`_updown_concat_features()`（第 134-177 行）

> **注意**：此模型当前为死代码（`_concat_downward()` 在第 588 行提前返回），但模型仍被加载。以下为特征工程的完整分析，供未来参考。

**31 维特征列表**：

| 编号 | 特征名 | 说明 | 类型 |
|------|--------|------|------|
| 1 | `is_in_same_row` | 是否在同一行（R 标签匹配） | 布尔 |
| 2 | `y_dis / max(h1,h2)` | Y 距离 / 最大高度比 | 浮点 |
| 3 | `page_diff` | 页码差（是否跨页） | 整数 |
| 4 | `is_same_layoutno` | 是否相同版面类型 | 布尔 |
| 5 | `up_is_text` | 上方文本是否为 text 版面 | 布尔 |
| 6 | `down_is_text` | 下方文本是否为 text 版面 | 布尔 |
| 7 | `up_is_table` | 上方是否为 table 版面 | 布尔 |
| 8 | `down_is_table` | 下方是否为 table 版面 | 布尔 |
| 9 | `up_end_sentence` | 上方以句末标点结尾 | 布尔 |
| 10 | `up_end_comma` | 上方以逗号/标点结尾 | 布尔 |
| 11 | `down_start_punct` | 下方以标点开头 | 布尔 |
| 12 | `up_end_close_paren` | 上方以右括号结尾 | 布尔 |
| 13 | `up_end_comma_nodot` | 上方以逗号结尾（非句号） | 布尔 |
| 14 | `dup_13` | 特征 13 的副本 | 布尔 |
| 15 | `paren_balance` | 上方有未闭括号且下方有闭括号 | 布尔 |
| 16 | `down_match_heading` | 下方匹配标题模式 | 布尔 |
| 17 | `down_start_upper` | 下方以大写字母开头 | 布尔 |
| 18 | `up_end_upper` | 上方以大写字母结尾 | 布尔 |
| 19 | `up_end_alnum` | 上方以字母数字结尾 | 布尔 |
| 20 | `down_is_number` | 下方全为数字/百分比 | 布尔 |
| 21 | `last2_match` | 上下末尾 2 字符相同 | 布尔 |
| 22 | `x_misalign` | 上方右侧 > 下方左侧（错位） | 布尔 |
| 23 | `height_diff_ratio` | 高度差异比 | 浮点 |
| 24 | `x_dis / char_width` | X 距离 / 字符宽度比 | 浮点 |
| 25 | `len_diff_ratio` | 文本长度差异比 | 浮点 |
| 26 | `merged_vs_individual_tokens` | 合并后 vs 独立 token 数 | 整数 |
| 27 | `down_up_token_diff` | 下方 - 上方 token 数差 | 整数 |
| 28 | `last_tokens_match` | 末尾 token 是否匹配 | 布尔 |
| 29 | `max_in_row` | 最大行内框数 | 整数 |
| 30 | `abs_in_row_diff` | 行内框数绝对差 | 整数 |
| 31 | `down_single_noun` | 下方为单个名词 token | 布尔 |
| 32 | `up_single_noun` | 上方为单个名词 token | 布尔 |

**标题模式匹配**（`_match_proj`）：

```python
# 支持 8 种中英文标题模式
patterns = [
    r"第[一二三四五六七八九十\d]+[章节]",  # 第X章/第X节
    r"[一二三四五六七八九十]+、",           # 一、二、...
    r"\d+[\.、]\d*[\.、]?\d*",            # 1. / 1.1 / 1.1.1
    r"[（(]\d+[)）]",                      # (1) / （1）
    r"[A-Z][\.\、]",                       # A. / A、
    r"[IVXLCDM]+[\.\、]",                  # I. / II. / III.
]
```

---

## 附录：代码文件索引

| 文件路径 | 行数 | 核心内容 |
|---------|------|---------|
| `deepdoc/parser/pdf_parser.py` | 1509 | PDF 核心解析器（RAGFlowPdfParser/PlainParser/VisionParser） |
| `deepdoc/parser/docx_parser.py` | 139 | Word 文档解析器 |
| `deepdoc/parser/excel_parser.py` | 270 | Excel/CSV 解析器（多引擎） |
| `deepdoc/parser/html_parser.py` | 213 | HTML 解析器 |
| `deepdoc/parser/ppt_parser.py` | 96 | PowerPoint 解析器 |
| `deepdoc/parser/txt_parser.py` | 64 | 纯文本解析器 |
| `deepdoc/parser/json_parser.py` | 179 | JSON/JSONL 解析器 |
| `deepdoc/parser/markdown_parser.py` | 321 | Markdown 解析器 |
| `deepdoc/parser/figure_parser.py` | 255 | Vision 图表描述器 |
| `deepdoc/parser/docling_parser.py` | 356 | IBM Docling 集成 |
| `deepdoc/parser/mineru_parser.py` | 673 | MinerU API 集成（7种后端） |
| `deepdoc/parser/paddleocr_parser.py` | 554 | PaddleOCR-VL API 集成 |
| `deepdoc/parser/tcadp_parser.py` | 547 | 腾讯云 LKEAP API 集成 |
| `deepdoc/vision/ocr.py` | 751 | OCR 引擎（TextDetector + TextRecognizer） |
| `deepdoc/vision/layout_recognizer.py` | 457 | 布局识别器（3种实现） |
| `deepdoc/vision/table_structure_recognizer.py` | 612 | 表格结构识别器 |
| `deepdoc/vision/recognizer.py` | 442 | 基础识别器类 |
| `deepdoc/vision/operators.py` | 733 | 图像预处理算子 |
| `deepdoc/vision/postprocess.py` | 370 | 后处理（DB/CTC） |

---

> **文档生成时间**：2026年6月  
> **分析代码版本**：ragflow-main（GitHub infiniflow/ragflow v0.23.1）
