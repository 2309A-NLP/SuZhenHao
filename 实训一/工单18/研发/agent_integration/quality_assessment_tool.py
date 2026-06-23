"""
RAGFlow Agent Tool 集成 — 文档质量评估

对应RAGFlow源码位置: agent/tools/document_quality_assessment.py
安装方式: 将本文件复制到 ragflow-main/agent/tools/ 目录下即可自动注册
"""

import logging
import json
import sys
from pathlib import Path
from typing import Any

from agent.tools.base import ToolParamBase, ToolMeta, ToolBase

logger = logging.getLogger(__name__)


class QualityAssessmentParam(ToolParamBase):
    """文档质量评估 Tool 参数定义"""

    def __init__(self):
        self.meta: ToolMeta = {
            "name": "document_quality_assessment",
            "displayName": "文档质量评估",
            "description": (
                "评估文档文件夹的质量，包括：格式分布统计、PDF页面类型识别（文字型/扫描型/混合型）、"
                "文档长度分布、重复检测（MD5精确+SimHash近似）、敏感信息检测。"
                "返回结构化JSON报告和HTML简报路径。"
            ),
            "parameters": {
                "folder_path": {
                    "type": "string",
                    "description": "待评估的文档文件夹路径",
                    "displayDescription": "文档目录路径",
                    "required": True,
                    "default": "",
                    "enum": [],
                },
                "output_dir": {
                    "type": "string",
                    "description": "报告输出目录（可选，默认为 ./quality_report）",
                    "displayDescription": "输出目录",
                    "required": False,
                    "default": "./quality_report",
                    "enum": [],
                },
                "config_path": {
                    "type": "string",
                    "description": "配置文件路径（可选，默认使用 assessment_config.yaml）",
                    "displayDescription": "配置文件",
                    "required": False,
                    "default": "",
                    "enum": [],
                },
            },
        }
        super().__init__()
        self.folder_path = ""
        self.output_dir = "./quality_report"
        self.config_path = ""

    def check(self):
        self.check_empty(self.folder_path, "Document folder path")


class QualityAssessmentTool(ToolBase):
    """RAGFlow Agent Tool — 文档质量评估"""

    def _invoke(self, folder_path: str, output_dir: str = "./quality_report",
                config_path: str = "", **kwargs) -> str:
        """
        执行文档质量评估

        Returns:
            JSON字符串，包含评估报告摘要和完整报告路径
        """
        folder = Path(folder_path)
        if not folder.is_dir():
            return json.dumps({
                "status": "error",
                "message": f"目录不存在: {folder_path}"
            }, ensure_ascii=False)

        # 动态导入评估脚本
        script_dir = Path(__file__).parent.parent / ".cursor" / "skills" / "document-quality-assessment" / "scripts"
        if not script_dir.is_dir():
            # 备选：同级目录
            script_dir = Path(__file__).parent.parent / "scripts"

        sys.path.insert(0, str(script_dir))

        try:
            from assess_documents import load_config, assess

            # 加载配置
            if config_path:
                config = load_config(config_path)
            else:
                default_config = Path(__file__).parent.parent / ".cursor" / "skills" / "document-quality-assessment" / "assessment_config.yaml"
                config = load_config(str(default_config) if default_config.is_file() else None)

            # 执行评估
            output = Path(output_dir)
            output.mkdir(parents=True, exist_ok=True)

            report = assess(
                input_dir=folder,
                config=config,
                recursive=True,
                do_classify=True,
            )

            # 保存报告
            json_path = output / "quality_report.json"
            html_path = output / "quality_brief.html"

            report.pop("_config", None)

            json_path.write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            # 生成摘要
            meta = report["meta"]
            summary = {
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
            }

            logger.info(f"文档质量评估完成: {meta['total_files']} 文件, 耗时 {meta['duration_seconds']}s")
            return json.dumps(summary, ensure_ascii=False, indent=2)

        except ImportError as e:
            return json.dumps({
                "status": "error",
                "message": f"缺少依赖: {e}. 请执行: pip install -r requirements.txt"
            }, ensure_ascii=False)
        except Exception as e:
            logger.exception("文档质量评估失败")
            return json.dumps({
                "status": "error",
                "message": str(e)
            }, ensure_ascii=False)
