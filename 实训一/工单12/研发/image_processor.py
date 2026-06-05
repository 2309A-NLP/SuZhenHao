"""
图片处理模块 - 基于阿里云百炼 Qwen-VL 模型的图片理解
支持图片描述、图表分析、OCR 文字提取、数据解读等功能
"""
import base64
import os
import re
from pathlib import Path
from typing import Dict, List, Optional

import requests

from config import (
    QWEN_VL_API_KEY,
    QWEN_VL_API_BASE,
    QWEN_VL_MODEL,
    IMAGE_DIR,
    MAX_IMAGE_SIZE_MB,
    SUPPORTED_IMAGE_FORMATS,
)


class ImageProcessor:
    """图片处理器 - 调用 Qwen-VL 模型进行图片理解。"""

    def __init__(
        self,
        api_key: str = QWEN_VL_API_KEY,
        api_base: str = QWEN_VL_API_BASE,
        model: str = QWEN_VL_MODEL,
    ):
        self.api_key = api_key or ""
        self.api_base = api_base.rstrip("/")
        self.model = model
        self.available = bool(self.api_key)
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _clean_output(text: str) -> str:
        """清理模型输出，去除无意义符号。"""
        import re
        # 去掉 markdown 标题符号 (# ## ### 等)
        text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
        # 去掉多余的 ** 加粗符号
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
        # 去掉多余的 --- 分隔线
        text = re.sub(r'^-{3,}\s*$', '', text, flags=re.MULTILINE)
        # 去掉多余空行（连续2个以上空行合并为1个）
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

    def encode_image(self, image_path: str) -> str:
        """将图片文件编码为 base64 字符串。"""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def get_mime_type(self, image_path: str) -> str:
        """根据文件扩展名获取 MIME 类型。"""
        ext = Path(image_path).suffix.lower()
        mime_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".bmp": "image/bmp",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mime_map.get(ext, "image/jpeg")

    def analyze_image(
        self,
        image_path: str,
        question: str = None,
        lang: str = "zh",
    ) -> Dict:
        """
        分析图片内容。

        Args:
            image_path: 图片文件路径
            question: 用户对图片的提问（可选，默认为通用描述）
            lang: 语言（zh/en）

        Returns:
            包含 analysis（分析结果）和 metadata（元数据）的字典
        """
        if not self.available:
            raise RuntimeError("未配置 QWEN_VL_API_KEY，请在 .env 文件中配置")

        if not os.path.exists(image_path):
            raise FileNotFoundError(f"图片文件未找到: {image_path}")

        # 验证文件格式
        ext = Path(image_path).suffix.lower()
        if ext not in SUPPORTED_IMAGE_FORMATS:
            raise ValueError(f"不支持的图片格式: {ext}，支持: {', '.join(SUPPORTED_IMAGE_FORMATS)}")

        # 验证文件大小
        size_mb = os.path.getsize(image_path) / (1024 * 1024)
        if size_mb > MAX_IMAGE_SIZE_MB:
            raise ValueError(f"图片文件过大: {size_mb:.1f}MB，最大支持 {MAX_IMAGE_SIZE_MB}MB")

        # 编码图片
        base64_image = self.encode_image(image_path)
        mime_type = self.get_mime_type(image_path)

        # 构建 prompt
        if question:
            prompt = question
        else:
            if lang == "en":
                prompt = (
                    "Please analyze this image in detail. Describe what you see, "
                    "including any text, charts, tables, or key information. "
                    "If it's a financial document or chart, extract the key data points."
                )
            else:
                prompt = (
                    "请详细分析这张图片。描述你看到的内容，包括文字、图表、表格或关键信息。"
                    "如果是金融文档或图表，请提取关键数据点。"
                )

        # 调用 Qwen-VL API
        try:
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_image}"
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
                "max_tokens": 2000,
                "temperature": 0.7,
            }

            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=60,
            )

            if response.status_code == 200:
                result = response.json()
                analysis = result["choices"][0]["message"]["content"]
                analysis = self._clean_output(analysis)
                return {
                    "analysis": analysis,
                    "image": os.path.basename(image_path),
                    "size_mb": round(size_mb, 2),
                    "model": self.model,
                    "question": question,
                }

            error_msg = response.json().get("error", {}).get("message", "未知错误")
            raise RuntimeError(f"Qwen-VL API 请求失败: {error_msg}")

        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"网络请求失败: {exc}") from exc

    def analyze_image_base64(
        self,
        base64_data: str,
        mime_type: str = "image/jpeg",
        question: str = None,
        lang: str = "zh",
    ) -> Dict:
        """
        分析 base64 编码的图片数据。

        Args:
            base64_data: base64 编码的图片数据
            mime_type: MIME 类型
            question: 用户提问
            lang: 语言

        Returns:
            分析结果字典
        """
        if not self.available:
            raise RuntimeError("未配置 QWEN_VL_API_KEY")

        if question:
            prompt = question
        else:
            if lang == "en":
                prompt = (
                    "Please analyze this image in detail. Describe what you see, "
                    "including any text, charts, tables, or key information. "
                    "If it's a financial document or chart, extract the key data points."
                )
            else:
                prompt = (
                    "请详细分析这张图片。描述你看到的内容，包括文字、图表、表格或关键信息。"
                    "如果是金融文档或图表，请提取关键数据点。"
                )

        try:
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{base64_data}"
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
                "max_tokens": 2000,
                "temperature": 0.7,
            }

            response = requests.post(
                f"{self.api_base}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=60,
            )

            if response.status_code == 200:
                result = response.json()
                analysis = result["choices"][0]["message"]["content"]
                analysis = self._clean_output(analysis)
                return {
                    "analysis": analysis,
                    "model": self.model,
                    "question": question,
                }

            error_msg = response.json().get("error", {}).get("message", "未知错误")
            raise RuntimeError(f"Qwen-VL API 请求失败: {error_msg}")

        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"网络请求失败: {exc}") from exc

    def test_connection(self) -> bool:
        """测试 Qwen-VL API 连接。"""
        if not self.available:
            print("⚠️  未配置 Qwen-VL API Key，跳过连接测试")
            return False

        try:
            print("测试 Qwen-VL API 连接...")
            # 创建一个简单的测试图片（1x1 红色像素 PNG）
            test_image_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
            result = self.analyze_image_base64(
                test_image_b64,
                mime_type="image/png",
                question="请描述这张图片的内容。",
            )
            print("✓ Qwen-VL API 连接成功")
            return True
        except Exception as exc:
            print(f"✗ Qwen-VL API 连接失败: {exc}")
            return False


def save_uploaded_image(file_content: bytes, filename: str) -> str:
    """保存上传的图片文件，返回保存路径。"""
    os.makedirs(IMAGE_DIR, exist_ok=True)

    # 处理文件名冲突
    base_name = Path(filename).stem
    ext = Path(filename).suffix
    save_path = os.path.join(IMAGE_DIR, filename)
    counter = 1
    while os.path.exists(save_path):
        save_path = os.path.join(IMAGE_DIR, f"{base_name}_{counter}{ext}")
        counter += 1

    with open(save_path, "wb") as f:
        f.write(file_content)

    return save_path


def get_image_info(image_path: str) -> Dict:
    """获取图片文件信息。"""
    path = Path(image_path)
    size_mb = path.stat().st_size / (1024 * 1024) if path.exists() else 0
    return {
        "name": path.name,
        "path": str(path),
        "size_mb": round(size_mb, 2),
        "format": path.suffix.lower(),
        "exists": path.exists(),
    }


if __name__ == "__main__":
    processor = ImageProcessor()
    processor.test_connection()
