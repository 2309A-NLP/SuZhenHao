# 导入操作系统相关模块，用于文件路径判断、文件大小获取、目录创建等操作
import os
# 导入类型注解工具，定义列表、字典、任意类型等类型提示，提升代码可读性
from typing import List, Dict, Any
# 导入LangChain文本分割器，用于将长文本切分为固定大小的文本块
from langchain.text_splitter import RecursiveCharacterTextSplitter

# 尝试导入PyMuPDF库，用于快速提取PDF文本
try:
    import pymupdf
# 如果导入失败（库未安装），将pymupdf设为None
except ImportError:
    pymupdf = None

# 尝试导入pdfplumber库，用于提取PDF文本和表格，保留较好布局
try:
    import pdfplumber
# 如果导入失败，将pdfplumber设为None
except ImportError:
    pdfplumber = None

# 尝试导入MinerU相关库，用于高精度解析复杂PDF（公式、图表、复杂排版）
try:
    from magic_pdf.pipe import UNIPipe
    from magic_pdf.rw.DiskReaderWriter import DiskReaderWriter
# 如果导入失败，将UNIPipe设为None
except ImportError:
    UNIPipe = None

# 尝试导入PaddleOCR库，用于对图片型PDF进行OCR文字识别
try:
    from paddleocr import PaddleOCR
# 如果导入失败，将PaddleOCR设为None
except ImportError:
    PaddleOCR = None


def load_pdf_with_pymupdf(pdf_path: str) -> str:
    """使用PyMuPDF提取文本（快速，适合纯文本）"""
    # 判断PDF文件是否存在，不存在则抛出文件未找到异常
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

    # 打开PDF文件
    doc = pymupdf.open(pdf_path)
    # 初始化空字符串，用于存储提取的文本
    text = ""
    # 遍历PDF的每一页
    for page in doc:
        # 提取当前页面的文本
        page_text = page.get_text()
        # 如果当前页面有文本，追加到总文本中
        if page_text:
            text += page_text
    # 关闭PDF文件
    doc.close()
    # 返回提取的完整文本
    return text


def load_pdf_with_pdfplumber(pdf_path: str) -> str:
    """使用pdfplumber提取文本+表格（保留布局较好）"""
    # 判断PDF文件是否存在
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

    # 初始化空字符串存储文本
    text = ""
    # 使用pdfplumber打开PDF文件（上下文管理器自动关闭）
    with pdfplumber.open(pdf_path) as pdf:
        # 遍历每一页
        for page in pdf.pages:
            # 提取当前页面文本
            page_text = page.extract_text()
            # 有文本则追加
            if page_text:
                text += page_text
    # 返回总文本
    return text


def load_pdf_with_mineru(pdf_path: str, output_dir: str = "./mineru_output") -> str:
    """使用MinerU解析（高精度，支持复杂布局、公式、图表）"""
    # 判断PDF文件是否存在
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

    # 创建输出目录（用于存储解析出的图片等资源），已存在则不报错
    os.makedirs(output_dir, exist_ok=True)

    try:
        # 创建MinerU的文件读写工具
        image_writer = DiskReaderWriter(output_dir)
        # 初始化MinerU解析管道
        pipe = UNIPipe(pdf_path, image_writer=image_writer)
        # 执行PDF分类
        pipe.pipe_classify()
        # 执行PDF内容解析
        pipe.pipe_parse()
        # 获取解析后的Markdown格式文本
        return pipe.get_markdown()
    except Exception as e:
        # 解析失败则抛出运行时异常
        raise RuntimeError(f"MinerU解析失败: {str(e)}")


def load_pdf_with_paddleocr_vl(pdf_path: str) -> str:
    """使用PaddleOCR-VL（多模态OCR，支持图表理解）"""
    # 判断PDF文件是否存在
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

    # 初始化PaddleOCR，开启角度检测，使用中文模型，关闭日志输出
    ocr = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
    # 对PDF执行OCR识别
    result = ocr.ocr(pdf_path, cls=True)

    # 初始化列表存储识别出的文本行
    text_lines = []
    # 遍历OCR结果的每一页
    for page in result:
        if page is not None:
            # 遍历当前页的每一行识别结果
            for line in page:
                # 校验结果格式是否合法
                if line and len(line) >= 2 and line[1] and len(line[1]) >= 1:
                    # 提取识别的文本内容，加入列表
                    text_lines.append(line[1][0])

    # 将所有文本行用换行符连接，返回最终文本
    return "\n".join(text_lines)


def parse_pdf(pdf_path: str, method: str = "auto") -> List[Dict[str, Any]]:
    """
    统一入口：解析PDF并返回文档块列表（兼容现有build_role_kb的分块格式）

    Args:
        pdf_path: PDF文件路径
        method: 解析方法，可选值: 'auto', 'pymupdf', 'pdfplumber', 'mineru', 'paddleocr'

    Returns:
        文档块列表，每个块包含 content, title, source 字段

    Raises:
        FileNotFoundError: PDF文件不存在
        ImportError: 所需解析库未安装
        ValueError: 未知解析方法
        RuntimeError: 解析过程中发生错误
    """
    # 判断文件是否存在
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF文件不存在: {pdf_path}")

    # 判断路径是否为有效文件
    if not os.path.isfile(pdf_path):
        raise ValueError(f"路径不是有效的文件: {pdf_path}")

    # 如果解析方法为auto（自动选择）
    if method == "auto":
        # 获取PDF文件大小
        file_size = os.path.getsize(pdf_path)
        # 如果文件大于5MB，优先使用pdfplumber（否则用pymupdf）
        if file_size > 5 * 1024 * 1024:
            method = "pdfplumber" if pdfplumber else "pymupdf"
        # 小文件优先使用pymupdf（更快）
        else:
            method = "pymupdf" if pymupdf else "pdfplumber"

    # 初始化原始文本为空字符串
    raw_text = ""
    # 根据指定的解析方法执行对应函数
    if method == "pymupdf":
        # 检查库是否已安装
        if pymupdf is None:
            raise ImportError("请安装PyMuPDF: pip install PyMuPDF")
        # 调用pymupdf解析函数
        raw_text = load_pdf_with_pymupdf(pdf_path)
    elif method == "pdfplumber":
        if pdfplumber is None:
            raise ImportError("请安装pdfplumber: pip install pdfplumber")
        raw_text = load_pdf_with_pdfplumber(pdf_path)
    elif method == "mineru":
        if UNIPipe is None:
            raise ImportError("请安装MinerU: pip install mineru[all]")
        raw_text = load_pdf_with_mineru(pdf_path)
    elif method == "paddleocr":
        if PaddleOCR is None:
            raise ImportError("请安装PaddleOCR: pip install paddleocr")
        raw_text = load_pdf_with_paddleocr_vl(pdf_path)
    # 未知解析方法，抛出异常
    else:
        raise ValueError(f"未知解析方法: {method}")

    # 如果解析后的文本为空，抛出异常
    if not raw_text or not raw_text.strip():
        raise RuntimeError("PDF解析结果为空，无法生成有效文档块")

    # 初始化文本分割器：块大小800字符，重叠120字符
    splitter = RecursiveCharacterTextSplitter(chunk_size=800, chunk_overlap=120)
    # 将原始文本分割成文本块列表
    chunks = splitter.split_text(raw_text)

    # 如果分割后没有有效块，抛出异常
    if not chunks:
        raise RuntimeError("文本分割后未得到有效块")

    # 获取PDF文件名（不带路径）
    pdf_basename = os.path.basename(pdf_path)

    # 构造并返回符合知识库格式的文档块列表
    return [
        {
            "content": chunk.strip(),  # 文本内容（去除首尾空白）
            "title": pdf_basename,  # 标题为PDF文件名
            "source": pdf_path,  # 来源为PDF完整路径
        }
        for chunk in chunks  # 遍历所有分割后的文本块
        if chunk.strip()  # 过滤空文本块
    ]