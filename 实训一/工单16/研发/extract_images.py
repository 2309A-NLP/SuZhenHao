#!/usr/bin/env python3
"""
工单16 - 从专利PDF中提取页面图片
方式一：使用 PyMuPDF (fitz) 将PDF每页渲染为图片

用法：python extract_images.py
输入：original_problems/documents/*.pdf
输出：/home/su/ragflow_vlm_data/images/{文档名}/page_{页码}.png
"""

import os
import re
import fitz  # PyMuPDF
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

# ========== 配置 ==========
PDF_DIR = "/mnt/c/Users/23672/Desktop/RAG 新工单/14-17附件/original_problems/documents"
IMAGE_DIR = "/home/su/ragflow_vlm_data/images"
QUESTIONS_FILE = "/mnt/c/Users/23672/Desktop/RAG 新工单/14-17附件/original_problems/questions.jsonl"
DPI = 200  # 清晰度，200 DPI 足够训练用，平衡质量和大小
MAX_WORKERS = 4  # 并行进程数


def get_required_pages(questions_file):
    """从 questions.jsonl 中提取每个文档需要的页码"""
    required = {}  # {doc_name: set of page numbers}
    
    with open(questions_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            item = eval(line)  # JSONL with Chinese chars, use eval for safety
            doc = item["document"]
            question = item["question"]
            
            if doc not in required:
                required[doc] = set()
            
            # 提取页码
            m = re.search(r"第(\d+)页", question)
            if m:
                page_num = int(m.group(1))
                required[doc].add(page_num)
            else:
                # group 1 纯文本题，标记为 0（表示需要第1页作为默认图片）
                required[doc].add(0)
    
    return required


def extract_pdf_images(pdf_path, output_dir, required_pages):
    """从单个PDF中提取指定页码的图片"""
    doc_name = Path(pdf_path).stem
    doc_dir = os.path.join(output_dir, doc_name)
    os.makedirs(doc_dir, exist_ok=True)
    
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"  ❌ 无法打开 {doc_name}: {e}")
        return 0
    
    total_pages = doc.page_count
    extracted = 0
    
    for page_num in required_pages:
        # page_num=0 表示需要第1页（默认图片）
        actual_page = max(1, page_num)
        
        if actual_page > total_pages:
            continue
        
        output_path = os.path.join(doc_dir, f"page_{actual_page:02d}.png")
        
        # 如果图片已存在，跳过
        if os.path.exists(output_path):
            extracted += 1
            continue
        
        try:
            page = doc[actual_page - 1]  # 0-indexed
            # 渲染为图片
            mat = fitz.Matrix(DPI / 72, DPI / 72)
            pix = page.get_pixmap(matrix=mat)
            pix.save(output_path)
            extracted += 1
        except Exception as e:
            print(f"  ⚠️ {doc_name} 第{actual_page}页提取失败: {e}")
    
    doc.close()
    return extracted


def main():
    print("=" * 60)
    print("工单16 - 从专利PDF中提取页面图片")
    print("=" * 60)
    
    # 1. 分析需要哪些页码
    print("\n[1/3] 分析 questions.jsonl 中的页码引用...")
    required = get_required_pages(QUESTIONS_FILE)
    total_docs = len(required)
    total_pages = sum(len(pages) for pages in required.values())
    print(f"  需要处理 {total_docs} 个文档，共 {total_pages} 个页面")
    
    # 2. 扫描可用的 PDF 文件
    print(f"\n[2/3] 扫描 PDF 目录: {PDF_DIR}")
    pdf_files = []
    for doc_name in required.keys():
        pdf_path = os.path.join(PDF_DIR, doc_name)
        if os.path.exists(pdf_path):
            pdf_files.append((pdf_path, doc_name))
        else:
            print(f"  ⚠️ 缺少 PDF: {doc_name}")
    print(f"  找到 {len(pdf_files)} 个 PDF 文件")
    
    # 3. 提取图片
    print(f"\n[3/3] 提取图片 (DPI={DPI}, 并行={MAX_WORKERS})...")
    os.makedirs(IMAGE_DIR, exist_ok=True)
    
    total_extracted = 0
    completed = 0
    
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {}
        for pdf_path, doc_name in pdf_files:
            pages = required[doc_name]
            future = executor.submit(extract_pdf_images, pdf_path, IMAGE_DIR, pages)
            futures[future] = doc_name
        
        for future in as_completed(futures):
            doc_name = futures[future]
            try:
                count = future.result()
                total_extracted += count
                completed += 1
                if completed % 100 == 0 or completed == len(pdf_files):
                    print(f"  进度: {completed}/{len(pdf_files)} 文档, 已提取 {total_extracted} 张图片")
            except Exception as e:
                print(f"  ❌ {doc_name} 处理异常: {e}")
    
    print(f"\n{'=' * 60}")
    print(f"完成！共提取 {total_extracted} 张图片")
    print(f"保存位置: {IMAGE_DIR}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
