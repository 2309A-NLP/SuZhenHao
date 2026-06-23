"""
RAGFlow API 端点 — 文档质量检查

对应RAGFlow源码位置: api/apps/document_quality_inspection_app.py
安装方式: 将本文件复制到 ragflow-main/api/apps/ 目录下，会自动注册路由

新增API端点:
  POST /v1/document/quality-inspection
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any

from quart import Blueprint, request
from api.utils.api_utils import get_json_result, get_data_error_result, server_error_response

logger = logging.getLogger(__name__)

# ============================================================
# Blueprint 定义
# ============================================================
page_name = "document_quality_inspection"
manager = Blueprint(page_name, __name__)


@manager.route("/quality-inspection", methods=["POST"])
async def quality_inspection():
    """
    POST /v1/document/quality-inspection

    Request Body (JSON):
        {
            "folder_path": "/path/to/documents",     // 必填：文件夹路径
            "output_dir": "./quality_report",         // 可选：输出目录
            "config_path": "",                        // 可选：配置文件路径
            "recursive": true                         // 可选：是否递归子目录
        }

    Response (JSON):
        {
            "code": 0,
            "data": {
                "status": "success",
                "total_files": 1700,
                "duration_seconds": 45.2,
                "format_summary": {...},
                "pdf_summary": {...},
                "duplicate_summary": {...},
                "sensitive_summary": {...},
                "classification_summary": {...},
                "report_json_path": "/path/to/quality_report.json",
                "report_html_path": "/path/to/quality_brief.html"
            },
            "message": "ok"
        }
    """
    try:
        body = await request.get_json()
        if not body:
            return get_data_error_result("请求体不能为空")

        folder_path = body.get("folder_path", "")
        if not folder_path:
            return get_data_error_result("folder_path 为必填参数")

        folder = Path(folder_path)
        if not folder.is_dir():
            return get_data_error_result(f"目录不存在: {folder_path}")

        output_dir = body.get("output_dir", str(folder / "quality_report"))
        config_path = body.get("config_path", "")
        recursive = body.get("recursive", True)

        # 加载评估模块
        skill_dir = Path(__file__).parent.parent / ".cursor" / "skills" / "document-quality-assessment"
        script_dir = skill_dir / "scripts"
        sys.path.insert(0, str(script_dir))

        from assess_documents import load_config, assess, render_html

        # 加载配置
        if config_path:
            config = load_config(config_path)
        else:
            default_config = skill_dir / "assessment_config.yaml"
            config = load_config(str(default_config) if default_config.is_file() else None)

        # 执行评估
        report = assess(
            input_dir=folder,
            config=config,
            recursive=recursive,
            do_classify=True,
        )

        # 保存报告
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)

        json_path = output / "quality_report.json"
        html_path = output / "quality_brief.html"

        report.pop("_config", None)

        json_path.write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        html_path.write_text(
            render_html(report),
            encoding="utf-8"
        )

        # 返回摘要 + 路径
        meta = report["meta"]
        data = {
            "status": "success",
            "total_files": meta["total_files"],
            "duration_seconds": meta["duration_seconds"],
            "errors_count": len(meta.get("errors", [])),
            "format_summary": report["format_distribution"]["summary"],
            "pdf_summary": report["pdf_page_types"]["summary"],
            "duplicate_summary": {
                "exact_groups": report["duplicates"]["exact"]["total_groups"],
                "approximate_pairs": report["duplicates"]["approximate"]["total_pairs"],
            },
            "sensitive_summary": report["sensitive_info"]["summary"],
            "classification_summary": report.get("classification", {}).get("tag_summary", {}),
            "report_json_path": str(json_path),
            "report_html_path": str(html_path),
        }

        return get_json_result(data=data)

    except Exception as e:
        logger.exception("质量检查API调用失败")
        return server_error_response(f"质量检查失败: {str(e)}")


@manager.route("/quality-inspection/<path:folder_path>", methods=["GET"])
async def quality_inspection_status(folder_path: str):
    """
    GET /v1/document/quality-inspection/<folder_path>

    检查指定目录是否已有质检报告（用于查询历史结果）
    """
    try:
        report_dir = Path(folder_path) / "quality_report"
        json_path = report_dir / "quality_report.json"

        if not json_path.is_file():
            return get_json_result(data={"has_report": False})

        with open(json_path, "r", encoding="utf-8") as f:
            report = json.load(f)

        return get_json_result(data={
            "has_report": True,
            "meta": report.get("meta", {}),
            "report_json_path": str(json_path),
            "report_html_path": str(report_dir / "quality_brief.html"),
        })

    except Exception as e:
        return server_error_response(str(e))
