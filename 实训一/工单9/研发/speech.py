"""
语音识别模块
- 支持音频文件转文字
- 使用Whisper本地模型（优先）或在线API（备选）
"""

import os
import tempfile


class SpeechRecognizer:
    def __init__(self):
        self.whisper_model = None
        self.backend = None
        self._init_backend()

    def _init_backend(self):
        """初始化语音识别后端"""
        # 尝试加载本地Whisper
        try:
            import whisper
            from config import WHISPER_MODEL_SIZE
            self.whisper_model = whisper.load_model(WHISPER_MODEL_SIZE)
            self.backend = "whisper"
            print(f"✅ Whisper {WHISPER_MODEL_SIZE} 模型加载成功")
            return
        except ImportError:
            print("⚠️ Whisper未安装，尝试备选方案...")

        # 备选：使用MiMo API的语音能力（如果有的话）
        try:
            from openai import OpenAI
            from config import MIMO_API_KEY, MIMO_BASE_URL
            self.client = OpenAI(api_key=MIMO_API_KEY, base_url=MIMO_BASE_URL)
            self.backend = "api"
            print("✅ 使用API语音识别模式")
        except Exception as e:
            print(f"❌ 语音识别初始化失败: {e}")
            self.backend = None

    def transcribe(self, audio_path: str) -> str:
        """
        将音频文件转为文字
        参数：audio_path - 音频文件路径
        返回：识别出的文字
        """
        if not self.backend:
            return "错误：语音识别模块未初始化"

        if self.backend == "whisper":
            return self._transcribe_whisper(audio_path)
        elif self.backend == "api":
            return self._transcribe_api(audio_path)

        return "错误：无可用的语音识别后端"

    def _transcribe_whisper(self, audio_path: str) -> str:
        """使用本地Whisper识别"""
        try:
            result = self.whisper_model.transcribe(
                audio_path,
                language=None,  # 自动检测语言
                task="transcribe"
            )
            return result["text"].strip()
        except Exception as e:
            return f"Whisper识别出错: {str(e)}"

    def _transcribe_api(self, audio_path: str) -> str:
        """使用API识别（OpenAI兼容格式）"""
        try:
            with open(audio_path, "rb") as audio_file:
                response = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file
                )
            return response.text.strip()
        except Exception as e:
            return f"API识别出错: {str(e)}"

    def is_available(self) -> bool:
        """检查语音识别是否可用"""
        return self.backend is not None
