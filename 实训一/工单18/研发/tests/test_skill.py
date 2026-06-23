#!/usr/bin/env python3
"""单元测试 — DocumentQualityAssessmentSkill"""

import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# 将脚本目录加入路径
SCRIPT_DIR = Path(__file__).parent.parent / ".cursor" / "skills" / "document-quality-assessment" / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

from assess_documents import (
    load_config,
    collect_files,
    file_extension,
    mask_sensitive,
    extract_context,
    compute_percentile,
    compute_simhash,
    hamming_distance,
    scan_sensitive,
    build_format_distribution,
    build_length_distribution,
    build_duplicates,
    build_sensitive_scan,
    classify_documents,
    assess,
)


# ============================================================
# 测试用临时目录创建
# ============================================================
@pytest.fixture
def sample_dir(tmp_path):
    """创建测试用文件样本目录"""
    # 文本文件
    (tmp_path / "readme.md").write_text("# Hello World\n这是一份测试文档。", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("简单的文本笔记内容。" * 50, encoding="utf-8")
    (tmp_path / "data.json").write_text('{"key": "value", "count": 42}', encoding="utf-8")
    (tmp_path / "report.html").write_text(
        "<html><body><h1>报告</h1><p>测试内容</p></body></html>",
        encoding="utf-8",
    )

    # 极短文件
    (tmp_path / "tiny.md").write_text("短", encoding="utf-8")

    # 重复文件
    content = "重复的内容 " * 100
    (tmp_path / "copy_a.txt").write_text(content, encoding="utf-8")
    (tmp_path / "copy_b.txt").write_text(content, encoding="utf-8")

    # 含敏感信息的文件
    (tmp_path / "contact.txt").write_text(
        "联系人：张三\n手机号：13812345678\n邮箱：zhangsan@example.com\n身份证：110101199001011234",
        encoding="utf-8",
    )

    # 不支持的格式
    (tmp_path / "image.xyz").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

    # 无扩展名文件
    (tmp_path / "noext").write_text("无扩展名的文件", encoding="utf-8")

    return tmp_path


@pytest.fixture
def config():
    """加载默认配置"""
    config_path = Path(__file__).parent.parent / ".cursor" / "skills" / "document-quality-assessment" / "assessment_config.yaml"
    if config_path.is_file():
        return load_config(str(config_path))
    return load_config(None)


# ============================================================
# 模块1: 格式分布统计
# ============================================================
class TestFormatDistribution:
    def test_counts_by_extension(self, sample_dir, config):
        files = collect_files(sample_dir, recursive=False)
        result = build_format_distribution(files, sample_dir, config)

        assert result["summary"]["total_files"] > 0
        assert result["summary"]["unique_extensions"] > 0
        assert ".txt" in result["by_extension"]
        assert ".md" in result["by_extension"]
        assert result["by_extension"][".txt"]["count"] >= 2  # notes.txt + copy_a.txt + copy_b.txt

    def test_percentage_sums_to_100(self, sample_dir, config):
        files = collect_files(sample_dir, recursive=False)
        result = build_format_distribution(files, sample_dir, config)

        total_pct = sum(info["percentage"] for info in result["by_extension"].values())
        assert abs(total_pct - 100.0) < 0.1

    def test_no_extension_file(self, sample_dir, config):
        files = collect_files(sample_dir, recursive=False)
        result = build_format_distribution(files, sample_dir, config)
        assert "(no_extension)" in result["by_extension"]


# ============================================================
# 模块2: PDF页面类型识别（需要pymupdf）
# ============================================================
class TestPdfPageTypes:
    def test_skips_non_pdf_files(self, sample_dir, config):
        files = collect_files(sample_dir, recursive=False)
        errors = []
        from assess_documents import ProgressTracker
        result = build_pdf_analysis(files, sample_dir, config, errors)
        # 没有PDF文件，结果应该为空
        assert result["summary"]["total_pdfs"] == 0


# ============================================================
# 模块3: 文档长度分布
# ============================================================
class TestLengthDistribution:
    def test_stats_computed(self, sample_dir, config):
        files = collect_files(sample_dir, recursive=False)
        errors = []
        result = build_length_distribution(files, sample_dir, config, errors)

        assert result["statistics"]["count"] > 0
        assert result["statistics"]["min"] >= 0
        assert result["statistics"]["max"] >= result["statistics"]["min"]
        assert result["statistics"]["p50"] > 0  # notes.txt有内容

    def test_buckets_populated(self, sample_dir, config):
        files = collect_files(sample_dir, recursive=False)
        errors = []
        result = build_length_distribution(files, sample_dir, config, errors)

        total_in_buckets = sum(result["buckets"].values())
        assert total_in_buckets == result["statistics"]["count"]


# ============================================================
# 模块4: 重复检测
# ============================================================
class TestDuplicates:
    def test_exact_duplicates_found(self, sample_dir, config):
        files = collect_files(sample_dir, recursive=False)
        errors = []
        result = build_duplicates(files, sample_dir, config, errors)

        assert result["exact"]["total_groups"] >= 1  # copy_a.txt 和 copy_b.txt
        assert result["exact"]["total_duplicate_files"] >= 2

    def test_md5_correct(self, sample_dir):
        # 验证copy_a和copy_b确实MD5相同
        md5_a = hashlib.md5((sample_dir / "copy_a.txt").read_bytes()).hexdigest()
        md5_b = hashlib.md5((sample_dir / "copy_b.txt").read_bytes()).hexdigest()
        assert md5_a == md5_b

    def test_hamming_distance_zero_for_same(self):
        val = 0b1010101010101010
        assert hamming_distance(val, val) == 0

    def test_hamming_distance_count(self):
        a = 0b0000
        b = 0b0011
        assert hamming_distance(a, b) == 2


# ============================================================
# 模块5: 敏感信息检测
# ============================================================
class TestSensitiveInfo:
    def test_phone_detected(self, sample_dir, config):
        files = collect_files(sample_dir, recursive=False)
        errors = []
        result = build_sensitive_scan(files, sample_dir, config, errors)

        phone_findings = [f for f in result["findings"] if f["type"] == "phone"]
        assert len(phone_findings) >= 1
        # 验证脱敏
        assert "138****5678" in phone_findings[0]["value_masked"]

    def test_email_detected(self, sample_dir, config):
        files = collect_files(sample_dir, recursive=False)
        errors = []
        result = build_sensitive_scan(files, sample_dir, config, errors)

        email_findings = [f for f in result["findings"] if f["type"] == "email"]
        assert len(email_findings) >= 1

    def test_id_card_detected(self, sample_dir, config):
        files = collect_files(sample_dir, recursive=False)
        errors = []
        result = build_sensitive_scan(files, sample_dir, config, errors)

        id_findings = [f for f in result["findings"] if f["type"] == "id_card"]
        assert len(id_findings) >= 1

    def test_context_provided(self, sample_dir, config):
        files = collect_files(sample_dir, recursive=False)
        errors = []
        result = build_sensitive_scan(files, sample_dir, config, errors)

        for finding in result["findings"]:
            assert len(finding["context"]) > 0
            assert "138" in finding["context"] or "@" in finding["context"] or "110101" in finding["context"]

    def test_masking_functions(self):
        assert mask_sensitive("13812345678", "phone") == "138****5678"
        assert "***" in mask_sensitive("test@example.com", "email")
        assert mask_sensitive("110101199001011234", "id_card").startswith("110")


# ============================================================
# 模块6: 文档分类标签
# ============================================================
class TestClassification:
    def test_short_doc_tagged(self, sample_dir, config):
        files = collect_files(sample_dir, recursive=False)
        errors = []
        length_result = build_length_distribution(files, sample_dir, config, errors)

        # 构建最小分析结果
        analysis = {
            "pdf_page_types": {"files": [], "summary": {"total_pdfs": 0, "by_document_type": {}}},
            "length_distribution": length_result,
            "duplicates": {"exact": {"groups": []}, "approximate": {"pairs": []}},
            "sensitive_info": {"findings": [], "summary": {"files_affected": 0}},
        }

        result = classify_documents(files, sample_dir, analysis, config)

        # tiny.md 应该被标记为 Short_Doc
        tags = result.get("file_tags", {})
        short_docs = [k for k, v in tags.items() if "Short_Doc" in v]
        assert len(short_docs) >= 1

    def test_duplicate_tagged(self, sample_dir, config):
        files = collect_files(sample_dir, recursive=False)
        errors = []
        dup_result = build_duplicates(files, sample_dir, config, errors)

        analysis = {
            "pdf_page_types": {"files": [], "summary": {"total_pdfs": 0, "by_document_type": {}}},
            "length_distribution": {"statistics": {}, "buckets": {}, "files": []},
            "duplicates": dup_result,
            "sensitive_info": {"findings": [], "summary": {"files_affected": 0}},
        }

        result = classify_documents(files, sample_dir, analysis, config)
        tags = result.get("file_tags", {})
        duplicates = [k for k, v in tags.items() if "Duplicate" in v]
        assert len(duplicates) >= 2


# ============================================================
# 完整评估测试
# ============================================================
class TestFullAssessment:
    def test_assess_runs(self, sample_dir, config):
        report = assess(
            input_dir=sample_dir,
            config=config,
            recursive=False,
            do_classify=True,
        )

        assert "meta" in report
        assert report["meta"]["total_files"] > 0
        assert "format_distribution" in report
        assert "pdf_page_types" in report
        assert "length_distribution" in report
        assert "duplicates" in report
        assert "sensitive_info" in report
        assert "classification" in report

    def test_assess_json_serializable(self, sample_dir, config):
        report = assess(
            input_dir=sample_dir,
            config=config,
            recursive=False,
            do_classify=True,
        )
        # 确保可以序列化为JSON
        json_str = json.dumps(report, ensure_ascii=False)
        assert len(json_str) > 0

    def test_assess_with_empty_dir(self, tmp_path, config):
        report = assess(
            input_dir=tmp_path,
            config=config,
            recursive=False,
            do_classify=True,
        )
        assert report["meta"]["total_files"] == 0


# ============================================================
# 配置测试
# ============================================================
class TestConfig:
    def test_load_default_config(self):
        config = load_config(None)
        assert "pdf_type" in config
        assert "duplicate" in config
        assert "sensitive" in config
        assert config["pdf_type"]["text_page_min_chars"] == 50

    def test_config_thresholds_customizable(self):
        config = load_config(None)
        config["pdf_type"]["text_page_min_chars"] = 100
        assert config["pdf_type"]["text_page_min_chars"] == 100


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
