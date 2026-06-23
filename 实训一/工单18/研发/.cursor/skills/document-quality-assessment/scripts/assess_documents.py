#!/usr/bin/env python3
"""Document corpus quality assessment — format, PDF types, length, duplicates, PII.

改进版：配置化阈值 + 文档分类标签 + 进度条 + SimHash性能优化 + 中断恢复
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    yaml = None

try:
    from tqdm import tqdm
except ImportError:
    tqdm = None

# ============================================================
# 常量（默认值，会被配置文件覆盖）
# ============================================================
TEXT_EXTENSIONS = {".txt", ".md", ".html", ".htm", ".json", ".csv", ".xml"}
LENGTH_EXTENSIONS = TEXT_EXTENSIONS | {".pdf", ".docx"}
PDF_EXTENSION = ".pdf"

PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\\d)")
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
ID_CARD_RE = re.compile(r"(?<!\d)\d{15}(?!\\d)|(?<!\d)\d{17}[\dXx](?!\\d)")

# ============================================================
# 全局状态：用于中断恢复
# ============================================================
_interrupted = False


def _signal_handler(sig, frame):
    global _interrupted
    _interrupted = True
    print("\n⚠️  收到中断信号，正在保存已完成的结果...", file=sys.stderr)


signal.signal(signal.SIGINT, _signal_handler)


# ============================================================
# 配置加载
# ============================================================
def load_config(config_path: str | None = None) -> dict:
    """加载配置文件，缺失则使用默认值"""
    default_config = {
        "format": {
            "supported_extensions": [
                ".pdf", ".docx", ".md", ".txt", ".html", ".htm",
                ".pptx", ".xlsx", ".csv", ".xml", ".json"
            ]
        },
        "pdf_type": {
            "text_page_min_chars": 50,
            "scan_ratio_threshold": 0.70,
            "text_ratio_threshold": 0.70,
        },
        "length": {
            "quantiles": [25, 50, 75, 90, 95],
            "buckets": [
                {"min": 0, "max": 500, "label": "极短(<500字)"},
                {"min": 500, "max": 2000, "label": "短(500-2000字)"},
                {"min": 2000, "max": 10000, "label": "中等(2000-10000字)"},
                {"min": 10000, "max": 50000, "label": "长(1万-5万字)"},
                {"min": 50000, "max": 999999999, "label": "超长(>5万字)"},
            ],
        },
        "duplicate": {
            "md5_check": True,
            "simhash_check": True,
            "simhash_threshold": 3,
            "size_ratio_skip": 3.0,
        },
        "sensitive": {
            "phone": True,
            "email": True,
            "id_card": True,
            "bank_card": False,
            "context_chars": 50,
        },
        "classification": {
            "tags": {
                "Text_PDF": "纯文字型PDF，可直接提取文本",
                "Scan_PDF": "扫描型PDF，需要OCR解析",
                "Mixed_PDF": "混合型PDF，部分页面需OCR",
                "Needs_OCR": "需要OCR处理的文档",
                "DOCX": "Word文档",
                "Markdown": "Markdown文档",
                "Short_Doc": "极短文档(<500字)",
                "Long_Doc": "超长文档(>5万字)",
                "Duplicate": "存在完全重复的文件",
                "Sensitive": "包含敏感信息的文件",
                "Unsupported": "不支持的文件格式",
            }
        },
    }

    if config_path and Path(config_path).is_file():
        if yaml is None:
            print("⚠️  pyyaml 未安装，使用默认配置", file=sys.stderr)
            return default_config
        with open(config_path, "r", encoding="utf-8") as f:
            user_cfg = yaml.safe_load(f) or {}
        # 深度合并
        _deep_merge(default_config, user_cfg)
        print(f"✅ 已加载配置: {config_path}", file=sys.stderr)

    return default_config


def _deep_merge(base: dict, override: dict):
    """递归合并字典"""
    for k, v in override.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


# ============================================================
# 进度条封装
# ============================================================
class ProgressTracker:
    """统一的进度跟踪器，支持 tqdm 或简单打印"""

    def __init__(self, total: int, desc: str = "处理中"):
        self.total = total
        self.desc = desc
        self.current = 0
        self.start_time = time.time()

        if tqdm:
            self.pbar = tqdm(total=total, desc=desc, unit="file", ncols=80)
        else:
            self.pbar = None
            print(f"🔄 {desc}: 0/{total}", file=sys.stderr)

    def update(self, n: int = 1, postfix: str = ""):
        self.current += n
        if self.pbar:
            self.pbar.update(n)
            if postfix:
                self.pbar.set_postfix_str(postfix)
        elif self.current % max(1, self.total // 10) == 0 or self.current == self.total:
            elapsed = time.time() - self.start_time
            speed = self.current / elapsed if elapsed > 0 else 0
            print(
                f"🔄 {desc}: {self.current}/{self.total} "
                f"({self.current/self.total*100:.0f}%) {speed:.1f} files/s",
                file=sys.stderr,
            )

    def close(self):
        if self.pbar:
            self.pbar.close()
        else:
            elapsed = time.time() - self.start_time
            print(f"✅ {self.desc} 完成: {self.current} 文件, 耗时 {elapsed:.1f}s", file=sys.stderr)


# ============================================================
# 基础工具函数
# ============================================================
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Document quality assessment — 文档质量评估工具"
    )
    parser.add_argument("--input", required=True, help="输入文档目录")
    parser.add_argument("--output-dir", default="./quality_report", help="报告输出目录")
    parser.add_argument(
        "--config",
        default=None,
        help="配置文件路径 (默认: assessment_config.yaml)",
    )
    parser.add_argument(
        "--simhash-threshold", type=int, default=None, help="覆盖SimHash阈值"
    )
    parser.add_argument(
        "--context-chars", type=int, default=None, help="覆盖敏感信息上下文长度"
    )
    parser.add_argument(
        "--recursive", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--no-classify", action="store_true", help="跳过分类标签")
    parser.add_argument("--resume", default=None, help="从之前的JSON报告恢复")
    return parser.parse_args()


def collect_files(root: Path, recursive: bool) -> list[Path]:
    if recursive:
        return [p for p in root.rglob("*") if p.is_file()]
    return [p for p in root.iterdir() if p.is_file()]


def rel_path(file_path: Path, root: Path) -> str:
    try:
        return str(file_path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(file_path).replace("\\", "/")


def file_extension(path: Path) -> str:
    ext = path.suffix.lower()
    return ext if ext else "(no_extension)"


def mask_sensitive(value: str, kind: str) -> str:
    if kind == "phone" and len(value) >= 7:
        return f"{value[:3]}****{value[-4:]}"
    if kind == "email" and "@" in value:
        local, domain = value.split("@", 1)
        prefix = local[:2] if len(local) >= 2 else local[:1]
        return f"{prefix}***@{domain}"
    if kind == "id_card" and len(value) >= 7:
        return f"{value[:3]}{'*' * (len(value) - 7)}{value[-4:]}"
    return "***"


def extract_context(text: str, start: int, end: int, context_chars: int) -> str:
    ctx_start = max(0, start - context_chars)
    ctx_end = min(len(text), end + context_chars)
    snippet = text[ctx_start:ctx_end]
    if ctx_start > 0:
        snippet = "..." + snippet
    if ctx_end < len(text):
        snippet = snippet + "..."
    return snippet


# ============================================================
# 文本提取
# ============================================================
def read_text_file(path: Path) -> str:
    for encoding in ("utf-8", "gbk", "gb2312", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def extract_pdf_text(path: Path) -> str | None:
    try:
        import fitz

        parts: list[str] = []
        with fitz.open(path) as doc:
            for page in doc:
                parts.append(page.get_text() or "")
        return "\n".join(parts)
    except Exception:
        return None


def extract_docx_text(path: Path) -> str | None:
    try:
        from docx import Document

        doc = Document(path)
        return "\n".join(p.text for p in doc.paragraphs)
    except Exception:
        return None


def extract_html_text(path: Path) -> str | None:
    try:
        from bs4 import BeautifulSoup

        html = read_text_file(path)
        soup = BeautifulSoup(html, "html.parser")
        return soup.get_text(separator="\n")
    except Exception:
        return None


def extract_text(path: Path) -> str | None:
    ext = path.suffix.lower()
    try:
        if ext in {".txt", ".md", ".csv", ".xml", ".json"}:
            return read_text_file(path)
        if ext in {".html", ".htm"}:
            return extract_html_text(path)
        if ext == ".pdf":
            return extract_pdf_text(path)
        if ext == ".docx":
            return extract_docx_text(path)
    except Exception:
        return None
    return None


# ============================================================
# 模块1: 格式分布统计
# ============================================================
def build_format_distribution(
    files: list[Path], root: Path, config: dict, progress: ProgressTracker | None = None
) -> dict[str, Any]:
    by_ext: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "total_size_bytes": 0}
    )
    for f in files:
        ext = file_extension(f)
        by_ext[ext]["count"] += 1
        try:
            by_ext[ext]["total_size_bytes"] += f.stat().st_size
        except OSError:
            pass
        if progress:
            progress.update()

    total = len(files) or 1
    for info in by_ext.values():
        info["percentage"] = round(info["count"] / total * 100, 2)

    most_common = (
        max(by_ext.items(), key=lambda x: x[1]["count"])[0] if by_ext else ""
    )
    return {
        "by_extension": dict(sorted(by_ext.items())),
        "summary": {
            "unique_extensions": len(by_ext),
            "most_common": most_common,
            "total_files": len(files),
        },
    }


# ============================================================
# 模块2: PDF 页面类型识别
# ============================================================
def analyze_pdf_pages(path: Path, min_chars: int) -> dict[str, Any] | None:
    try:
        import fitz

        with fitz.open(path) as doc:
            breakdown = Counter()
            for page in doc:
                text = (page.get_text() or "").strip()
                text_len = len(text)
                has_images = len(page.get_images(full=True)) > 0

                if text_len >= min_chars and has_images:
                    breakdown["mixed"] += 1
                elif text_len >= min_chars:
                    breakdown["text"] += 1
                elif has_images:
                    breakdown["scanned"] += 1
                else:
                    breakdown["empty"] += 1

            total = sum(breakdown.values()) or 1

            # 文档级类型判定
            doc_type = breakdown.most_common(1)[0][0] if breakdown else "empty"
            if len(breakdown) > 1:
                top_count = breakdown.most_common(1)[0][1]
                tied = [k for k, v in breakdown.items() if v == top_count]
                if len(tied) > 1:
                    doc_type = "mixed"

            return {
                "total_pages": total,
                "page_breakdown": dict(breakdown),
                "document_type": doc_type,
                "text_page_ratio": round(breakdown.get("text", 0) / total, 4),
            }
    except Exception:
        return None


def build_pdf_analysis(
    files: list[Path], root: Path, config: dict, errors: list[dict[str, str]],
    progress: ProgressTracker | None = None,
) -> dict[str, Any]:
    pdf_files = [f for f in files if f.suffix.lower() == PDF_EXTENSION]
    results: list[dict[str, Any]] = []
    type_counter: Counter[str] = Counter()
    min_chars = config["pdf_type"]["text_page_min_chars"]

    for f in pdf_files:
        analysis = analyze_pdf_pages(f, min_chars)
        if analysis is None:
            errors.append({"file": rel_path(f, root), "error": "PDF解析失败（文件可能损坏）"})
        else:
            entry = {"path": rel_path(f, root), **analysis}
            results.append(entry)
            type_counter[analysis["document_type"]] += 1
        if progress:
            progress.update()

    return {
        "files": results,
        "summary": {
            "total_pdfs": len(results),
            "by_document_type": dict(type_counter),
        },
    }


# ============================================================
# 模块3: 文档长度分布
# ============================================================
def compute_percentile(values: list[int], pct: float) -> int:
    if not values:
        return 0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * pct / 100
    f = int(k)
    c = min(f + 1, len(sorted_vals) - 1)
    if f == c:
        return sorted_vals[f]
    return int(sorted_vals[f] + (sorted_vals[c] - sorted_vals[f]) * (k - f))


def build_length_distribution(
    files: list[Path], root: Path, config: dict, errors: list[dict[str, str]],
    progress: ProgressTracker | None = None,
) -> dict[str, Any]:
    file_lengths: list[dict[str, Any]] = []
    counts: list[int] = []
    buckets_cfg = config["length"]["buckets"]
    quantiles = config["length"]["quantiles"]

    for f in files:
        if f.suffix.lower() not in LENGTH_EXTENSIONS:
            if progress:
                progress.update()
            continue
        text = extract_text(f)
        if text is None:
            errors.append({"file": rel_path(f, root), "error": "文本提取失败"})
        else:
            char_count = len(text)
            counts.append(char_count)
            file_lengths.append({"path": rel_path(f, root), "char_count": char_count})
        if progress:
            progress.update()

    # 按区间统计
    buckets = {b["label"]: 0 for b in buckets_cfg}
    for c in counts:
        for b in buckets_cfg:
            if b["min"] <= c < b["max"]:
                buckets[b["label"]] += 1
                break

    # 统计信息
    stats: dict[str, Any] = {"count": len(counts)}
    if counts:
        stats["min"] = min(counts)
        stats["max"] = max(counts)
        stats["mean"] = round(statistics.mean(counts), 2)
        for q in quantiles:
            stats[f"p{q}"] = compute_percentile(counts, q)
    else:
        stats.update({"min": 0, "max": 0, "mean": 0.0})
        for q in quantiles:
            stats[f"p{q}"] = 0

    return {
        "statistics": stats,
        "buckets": buckets,
        "files": file_lengths,
    }


# ============================================================
# 模块4: 重复检测（MD5 + SimHash）
# ============================================================
def compute_simhash(text: str) -> int | None:
    try:
        from simhash import Simhash

        if not text.strip():
            return None
        return Simhash(text).value
    except Exception:
        return None


def hamming_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def build_duplicates(
    files: list[Path], root: Path, config: dict, errors: list[dict[str, str]],
    progress: ProgressTracker | None = None,
) -> dict[str, Any]:
    dup_cfg = config["duplicate"]

    # --- MD5 精确匹配 ---
    md5_groups: dict[str, list[str]] = defaultdict(list)
    md5_sizes: dict[str, int] = {}

    if dup_cfg["md5_check"]:
        for f in files:
            try:
                content = f.read_bytes()
                digest = hashlib.md5(content).hexdigest()
                rel = rel_path(f, root)
                md5_groups[digest].append(rel)
                md5_sizes[digest] = len(content)
            except OSError as e:
                errors.append({"file": rel_path(f, root), "error": f"MD5读取失败: {e}"})
            if progress:
                progress.update()

    exact_groups = []
    dup_file_count = 0
    for digest, paths in md5_groups.items():
        if len(paths) > 1:
            exact_groups.append({
                "md5": digest,
                "files": sorted(paths),
                "size_bytes": md5_sizes[digest],
            })
            dup_file_count += len(paths)

    # --- SimHash 近似匹配（优化版） ---
    approx_pairs: list[dict[str, Any]] = []
    if dup_cfg["simhash_check"]:
        text_hashes: list[tuple[str, int, int]] = []  # (path, simhash, size)
        for f in files:
            if f.suffix.lower() not in LENGTH_EXTENSIONS:
                continue
            text = extract_text(f)
            if not text or not text.strip():
                continue
            sh = compute_simhash(text)
            if sh is not None:
                try:
                    size = f.stat().st_size
                except OSError:
                    size = 0
                text_hashes.append((rel_path(f, root), sh, size))

        # 性能优化：跳过文件大小差异过大的对
        size_ratio = dup_cfg.get("size_ratio_skip", 3.0)
        threshold = dup_cfg["simhash_threshold"]

        total_comparisons = len(text_hashes) * (len(text_hashes) - 1) // 2
        skipped = 0
        for i in range(len(text_hashes)):
            path_a, hash_a, size_a = text_hashes[i]
            for j in range(i + 1, len(text_hashes)):
                path_b, hash_b, size_b = text_hashes[j]
                # 大小差异过大，跳过
                if size_a > 0 and size_b > 0:
                    ratio = max(size_a, size_b) / max(min(size_a, size_b), 1)
                    if ratio > size_ratio:
                        skipped += 1
                        continue
                dist = hamming_distance(hash_a, hash_b)
                if dist <= threshold:
                    approx_pairs.append({
                        "file_a": path_a,
                        "file_b": path_b,
                        "hamming_distance": dist,
                        "similarity": round(1 - dist / 64, 4),
                    })

        if total_comparisons > 0:
            print(
                f"📊 SimHash: 比较 {total_comparisons} 对, 跳过 {skipped} 对(大小差异), 命中 {len(approx_pairs)} 对",
                file=sys.stderr,
            )

    return {
        "exact": {
            "groups": exact_groups,
            "total_groups": len(exact_groups),
            "total_duplicate_files": dup_file_count,
        },
        "approximate": {
            "pairs": approx_pairs,
            "threshold": dup_cfg["simhash_threshold"],
            "total_pairs": len(approx_pairs),
        },
    }


# ============================================================
# 模块5: 敏感信息检测
# ============================================================
def scan_sensitive(text: str, file_rel: str, context_chars: int) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    patterns = [
        ("phone", PHONE_RE),
        ("email", EMAIL_RE),
        ("id_card", ID_CARD_RE),
    ]
    for kind, pattern in patterns:
        for match in pattern.finditer(text):
            value = match.group()
            findings.append({
                "file": file_rel,
                "type": kind,
                "value_masked": mask_sensitive(value, kind),
                "position": match.start(),
                "context": extract_context(text, match.start(), match.end(), context_chars),
            })
    return findings


def build_sensitive_scan(
    files: list[Path], root: Path, config: dict, errors: list[dict[str, str]],
    progress: ProgressTracker | None = None,
) -> dict[str, Any]:
    sens_cfg = config["sensitive"]
    context_chars = sens_cfg["context_chars"]
    findings: list[dict[str, Any]] = []
    scannable = TEXT_EXTENSIONS | {".pdf", ".docx"}

    for f in files:
        if f.suffix.lower() not in scannable:
            if progress:
                progress.update()
            continue
        text = extract_text(f)
        if text is not None:
            rel = rel_path(f, root)
            try:
                findings.extend(scan_sensitive(text, rel, context_chars))
            except Exception as e:
                errors.append({"file": rel, "error": f"敏感信息检测失败: {e}"})
        if progress:
            progress.update()

    type_counter = Counter(f["type"] for f in findings)
    affected = len({f["file"] for f in findings})

    return {
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "by_type": dict(type_counter),
            "files_affected": affected,
        },
    }


# ============================================================
# 模块6: 文档分类标签体系
# ============================================================
def classify_documents(
    files: list[Path],
    root: Path,
    analysis_results: dict[str, Any],
    config: dict,
) -> dict[str, Any]:
    """根据各模块分析结果，为每个文件打分类标签"""
    class_cfg = config["classification"]
    file_tags: dict[str, list[str]] = defaultdict(list)

    # 1. 根据PDF类型打标签
    for pdf_info in analysis_results.get("pdf_page_types", {}).get("files", []):
        fpath = pdf_info["path"]
        doc_type = pdf_info["document_type"]
        tag_map = {
            "text": "Text_PDF",
            "scanned": "Scan_PDF",
            "mixed": "Mixed_PDF",
        }
        tag = tag_map.get(doc_type)
        if tag:
            file_tags[fpath].append(tag)
        if doc_type in ("scanned", "mixed"):
            file_tags[fpath].append("Needs_OCR")

    # 2. 根据文件扩展名打标签
    for f in files:
        rel = rel_path(f, root)
        ext = f.suffix.lower()
        if ext == ".docx":
            file_tags[rel].append("DOCX")
        elif ext == ".md":
            file_tags[rel].append("Markdown")

    # 3. 根据文档长度打标签
    for file_info in analysis_results.get("length_distribution", {}).get("files", []):
        fpath = file_info["path"]
        char_count = file_info["char_count"]
        if char_count < 500:
            file_tags[fpath].append("Short_Doc")
        elif char_count > 50000:
            file_tags[fpath].append("Long_Doc")

    # 4. 重复文件打标签
    for group in analysis_results.get("duplicates", {}).get("exact", {}).get("groups", []):
        for fpath in group["files"]:
            file_tags[fpath].append("Duplicate")
    for pair in analysis_results.get("duplicates", {}).get("approximate", {}).get("pairs", []):
        file_tags[pair["file_a"]].append("Duplicate")
        file_tags[pair["file_b"]].append("Duplicate")

    # 5. 敏感信息文件打标签
    sensitive_files = {
        f["file"] for f in analysis_results.get("sensitive_info", {}).get("findings", [])
    }
    for fpath in sensitive_files:
        file_tags[fpath].append("Sensitive")

    # 6. 不支持的格式打标签
    supported = set(config["format"]["supported_extensions"])
    for f in files:
        rel = rel_path(f, root)
        if f.suffix.lower() not in supported and "(no_extension)" not in rel:
            file_tags[rel].append("Unsupported")

    # 统计各标签数量
    tag_counts = Counter()
    for tags in file_tags.values():
        for tag in tags:
            tag_counts[tag] += 1

    return {
        "file_tags": dict(file_tags),
        "tag_summary": dict(tag_counts),
        "total_classified": len(file_tags),
    }


# ============================================================
# HTML报告生成
# ============================================================
def render_html(report: dict[str, Any]) -> str:
    meta = report["meta"]
    fmt = report["format_distribution"]
    pdf = report["pdf_page_types"]
    length = report["length_distribution"]
    dups = report["duplicates"]
    sens = report["sensitive_info"]
    classification = report.get("classification", {})
    stats = length["statistics"]

    # 格式分布行
    fmt_rows = ""
    for ext, info in fmt["by_extension"].items():
        fmt_rows += (
            f'<tr><td>{escape(str(ext))}</td><td>{info["count"]}</td>'
            f'<td>{info["percentage"]}%</td><td>{info["total_size_bytes"]:,}</td></tr>'
        )

    # PDF行
    pdf_rows = ""
    for item in pdf["files"][:50]:
        pb = item["page_breakdown"]
        pdf_rows += (
            f'<tr><td>{escape(item["path"])}</td><td>{item["document_type"]}</td>'
            f"<td>{item['total_pages']}</td>"
            f"<td>{pb.get('text', 0)}</td><td>{pb.get('scanned', 0)}</td>"
            f"<td>{pb.get('mixed', 0)}</td></tr>"
        )

    # 长度分布条形图
    bucket_max = max(length["buckets"].values()) or 1
    bucket_bars = ""
    for name, count in length["buckets"].items():
        width = int(count / bucket_max * 100)
        bucket_bars += (
            f'<div class="bar-row"><span class="label">{escape(name)}</span>'
            f'<div class="bar" style="width:{width}%"></div>'
            f'<span class="count">{count}</span></div>'
        )

    # 敏感信息行
    sens_rows = ""
    for item in sens["findings"][:30]:
        sens_rows += (
            f'<tr><td>{escape(item["file"])}</td><td>{escape(item["type"])}</td>'
            f"<td>{escape(item['value_masked'])}</td>"
            f'<td><code>{escape(item["context"][:120])}</code></td></tr>'
        )

    # 分类标签
    classification_html = ""
    if classification:
        tag_summary = classification.get("tag_summary", {})
        tag_cards = ""
        for tag, count in sorted(tag_summary.items(), key=lambda x: -x[1]):
            desc = class_cfg = report.get("_config", {}).get("classification", {}).get("tags", {}).get(tag, "")
            tag_cards += (
                f'<div class="card"><div class="value">{count}</div>'
                f'<div class="label">{escape(tag)}</div></div>'
            )
        classification_html = f"""
<h2>6. 文档分类标签</h2>
<p>共分类 {classification.get('total_classified', 0)} 个文件</p>
<div class="cards">{tag_cards}</div>
"""

    pdf_summary = pdf["summary"]["by_document_type"]
    sens_summary = sens["summary"]["by_type"]

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>文档质量评估简报</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2rem; color: #1a1a2e; background: #f8f9fc; }}
  h1 {{ color: #16213e; border-bottom: 3px solid #0f3460; padding-bottom: 0.5rem; }}
  h2 {{ color: #0f3460; margin-top: 2rem; }}
  .meta {{ background: #e8eaf6; padding: 1rem; border-radius: 8px; margin-bottom: 1.5rem; }}
  .cards {{ display: flex; flex-wrap: wrap; gap: 1rem; margin: 1rem 0; }}
  .card {{ background: white; border-radius: 8px; padding: 1rem 1.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); min-width: 120px; }}
  .card .value {{ font-size: 1.5rem; font-weight: bold; color: #0f3460; }}
  .card .label {{ font-size: 0.85rem; color: #666; }}
  table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); margin: 1rem 0; }}
  th {{ background: #0f3460; color: white; padding: 0.6rem 1rem; text-align: left; }}
  td {{ padding: 0.5rem 1rem; border-bottom: 1px solid #eee; }}
  tr:hover td {{ background: #f0f4ff; }}
  .bar-row {{ display: flex; align-items: center; gap: 0.5rem; margin: 0.4rem 0; }}
  .bar-row .label {{ width: 100px; font-size: 0.9rem; }}
  .bar {{ height: 20px; background: linear-gradient(90deg, #0f3460, #533483); border-radius: 4px; min-width: 2px; }}
  .bar-row .count {{ font-weight: bold; min-width: 30px; }}
  code {{ font-size: 0.8rem; background: #f0f0f0; padding: 2px 4px; border-radius: 3px; }}
  .warn {{ color: #e94560; font-weight: bold; }}
</style>
</head>
<body>
<h1>DocumentQualityAssessmentSkill — 文档质量评估简报</h1>
<div class="meta">
  <strong>扫描目录：</strong>{escape(meta['input_dir'])}<br>
  <strong>扫描时间：</strong>{escape(meta['scanned_at'])}<br>
  <strong>文件总数：</strong>{meta['total_files']} &nbsp;|&nbsp;
  <strong>总大小：</strong>{meta['total_size_bytes']:,} bytes &nbsp;|&nbsp;
  <strong>耗时：</strong>{meta['duration_seconds']}s
</div>

<h2>1. 格式分布统计</h2>
<p>最常见格式：<strong>{escape(fmt['summary']['most_common'])}</strong>（共 {fmt['summary']['unique_extensions']} 种扩展名）</p>
<table>
  <tr><th>扩展名</th><th>数量</th><th>占比</th><th>总大小(bytes)</th></tr>
  {fmt_rows}
</table>

<h2>2. PDF 页面类型识别</h2>
<div class="cards">
  <div class="card"><div class="value">{pdf['summary']['total_pdfs']}</div><div class="label">PDF 总数</div></div>
  <div class="card"><div class="value">{pdf_summary.get('text', 0)}</div><div class="label">文字型</div></div>
  <div class="card"><div class="value">{pdf_summary.get('scanned', 0)}</div><div class="label">扫描型</div></div>
  <div class="card"><div class="value">{pdf_summary.get('mixed', 0)}</div><div class="label">混合型</div></div>
</div>
<table>
  <tr><th>文件</th><th>文档类型</th><th>总页数</th><th>文字页</th><th>扫描页</th><th>混合页</th></tr>
  {pdf_rows}
</table>

<h2>3. 文档长度分布</h2>
<div class="cards">
  <div class="card"><div class="value">{stats.get('p50', 0):,}</div><div class="label">中位数(P50)</div></div>
  <div class="card"><div class="value">{stats.get('p25', 0):,}</div><div class="label">P25</div></div>
  <div class="card"><div class="value">{stats.get('p75', 0):,}</div><div class="label">P75</div></div>
  <div class="card"><div class="value">{stats.get('p95', 0):,}</div><div class="label">P95</div></div>
  <div class="card"><div class="value">{stats.get('mean', 0):,}</div><div class="label">均值</div></div>
</div>
{bucket_bars}

<h2>4. 重复检测</h2>
<div class="cards">
  <div class="card"><div class="value">{dups['exact']['total_groups']}</div><div class="label">MD5 精确重复组</div></div>
  <div class="card"><div class="value">{dups['exact']['total_duplicate_files']}</div><div class="label">涉及文件数</div></div>
  <div class="card"><div class="value">{dups['approximate']['total_pairs']}</div><div class="label">SimHash 近似对</div></div>
</div>

<h2>5. 敏感信息检测</h2>
<div class="cards">
  <div class="card"><div class="value warn">{sens['summary']['total_findings']}</div><div class="label">总命中</div></div>
  <div class="card"><div class="value">{sens['summary']['files_affected']}</div><div class="label">涉及文件</div></div>
  <div class="card"><div class="value">{sens_summary.get('phone', 0)}</div><div class="label">手机号</div></div>
  <div class="card"><div class="value">{sens_summary.get('email', 0)}</div><div class="label">邮箱</div></div>
  <div class="card"><div class="value">{sens_summary.get('id_card', 0)}</div><div class="label">身份证</div></div>
</div>
<table>
  <tr><th>文件</th><th>类型</th><th>脱敏值</th><th>上下文</th></tr>
  {sens_rows}
</table>

{classification_html}

<footer style="margin-top:3rem;color:#999;font-size:0.8rem;">
  Generated by DocumentQualityAssessmentSkill
</footer>
</body>
</html>"""


# ============================================================
# 主评估流程
# ============================================================
def assess(
    input_dir: Path,
    config: dict,
    simhash_threshold_override: int | None = None,
    context_chars_override: int | None = None,
    recursive: bool = True,
    do_classify: bool = True,
) -> dict[str, Any]:
    """主入口：对文件夹执行完整质量评估"""
    start = time.time()
    errors: list[dict[str, str]] = []

    # 覆盖配置
    if simhash_threshold_override is not None:
        config["duplicate"]["simhash_threshold"] = simhash_threshold_override
    if context_chars_override is not None:
        config["sensitive"]["context_chars"] = context_chars_override

    # 收集文件
    files = collect_files(input_dir, recursive)
    total_size = 0
    for f in files:
        try:
            total_size += f.stat().st_size
        except OSError:
            pass

    total = len(files)
    print(f"📁 发现 {total} 个文件, 总大小 {total_size:,} bytes", file=sys.stderr)

    # 进度跟踪
    p_format = ProgressTracker(total, "格式统计")
    p_pdf = ProgressTracker(
        len([f for f in files if f.suffix.lower() == PDF_EXTENSION]),
        "PDF分析",
    )
    p_length = ProgressTracker(total, "长度分析")
    p_dup = ProgressTracker(total, "重复检测")
    p_sensitive = ProgressTracker(total, "敏感信息")

    report: dict[str, Any] = {
        "meta": {
            "input_dir": str(input_dir.resolve()),
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "total_files": total,
            "total_size_bytes": total_size,
            "duration_seconds": 0.0,
            "errors": errors,
            "config_used": {
                "pdf_min_chars": config["pdf_type"]["text_page_min_chars"],
                "simhash_threshold": config["duplicate"]["simhash_threshold"],
                "context_chars": config["sensitive"]["context_chars"],
            },
        },
        "format_distribution": build_format_distribution(files, input_dir, config, p_format),
        "pdf_page_types": build_pdf_analysis(files, input_dir, config, errors, p_pdf),
        "length_distribution": build_length_distribution(files, input_dir, config, errors, p_length),
        "duplicates": build_duplicates(files, input_dir, config, errors, p_dup),
        "sensitive_info": build_sensitive_scan(files, input_dir, config, errors, p_sensitive),
    }

    # 关闭进度条
    for p in [p_format, p_pdf, p_length, p_dup, p_sensitive]:
        p.close()

    # 文档分类标签
    if do_classify:
        report["classification"] = classify_documents(files, input_dir, report, config)

    report["meta"]["duration_seconds"] = round(time.time() - start, 2)
    report["_config"] = config  # 供HTML渲染使用

    return report


# ============================================================
# 入口
# ============================================================
def main() -> None:
    args = parse_args()

    # 查找配置文件
    config_path = args.config
    if config_path is None:
        # 在脚本同级目录查找
        script_dir = Path(__file__).parent.parent
        candidate = script_dir / "assessment_config.yaml"
        if candidate.is_file():
            config_path = str(candidate)

    config = load_config(config_path)

    input_dir = Path(args.input).resolve()
    output_dir = Path(args.output_dir).resolve()

    if not input_dir.is_dir():
        raise SystemExit(f"输入目录不存在: {input_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)

    # 中断恢复
    if args.resume and Path(args.resume).is_file():
        with open(args.resume, "r", encoding="utf-8") as f:
            existing = json.load(f)
        print(f"📂 从 {args.resume} 恢复，已跳过已完成的分析", file=sys.stderr)
        # 简单恢复：保留meta，重新运行
        report = assess(
            input_dir, config,
            args.simhash_threshold, args.context_chars,
            args.recursive, not args.no_classify,
        )
        report["meta"]["resumed_from"] = args.resume
    else:
        report = assess(
            input_dir, config,
            args.simhash_threshold, args.context_chars,
            args.recursive, not args.no_classify,
        )

    # 保存报告
    json_path = output_dir / "quality_report.json"
    html_path = output_dir / "quality_brief.html"

    # 移除 _config（不写入JSON）
    report.pop("_config", None)

    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    html_path.write_text(render_html(report), encoding="utf-8")

    print(f"\n{'='*50}", file=sys.stderr)
    print(f"📄 JSON报告: {json_path}", file=sys.stderr)
    print(f"🌐 HTML简报: {html_path}", file=sys.stderr)
    print(f"📊 文件总数: {report['meta']['total_files']}", file=sys.stderr)
    print(f"⏱️  总耗时:   {report['meta']['duration_seconds']}s", file=sys.stderr)
    if report["meta"]["errors"]:
        print(f"⚠️  错误数:   {len(report['meta']['errors'])}", file=sys.stderr)
    if report.get("classification"):
        print(f"🏷️  分类标签: {len(report['classification']['tag_summary'])} 种", file=sys.stderr)
    print(f"{'='*50}", file=sys.stderr)


if __name__ == "__main__":
    main()
