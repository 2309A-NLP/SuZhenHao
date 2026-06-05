"""FastAPI 后端 - 为聊天前端提供问答接口"""
import sys
import tempfile
import os
from pathlib import Path
from typing import Optional

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app_core import get_doc_info, get_qa_system

ROOT = Path(__file__).parent
FRONTEND = ROOT / "frontend"

# 尝试导入语音识别库
_stt_available = False
try:
    import speech_recognition as sr
    _stt_available = True
except ImportError:
    pass

app = FastAPI(title="招股说明书智能问答 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    lang: str = Field(default="zh", pattern="^(zh|en)$")


class ChatResponse(BaseModel):
    query: str
    answer: str
    confidence: float
    sources: list
    intent: Optional[str] = None


@app.on_event("startup")
def warmup():
    """启动时预加载模型与索引"""
    try:
        get_qa_system()
    except Exception as exc:
        print(f"[警告] 启动预加载失败: {exc}")


@app.get("/")
async def index():
    return FileResponse(FRONTEND / "index.html")


@app.get("/api/health")
async def health():
    return {"status": "ok"}


@app.get("/api/doc-info")
async def doc_info():
    return get_doc_info()


@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="问题不能为空")

    try:
        qa = get_qa_system()
        intent = None
        if qa.query_processor:
            processed = qa.query_processor.process_query(query)
            intent = processed.get("intent")

        lang = getattr(body, 'lang', 'zh') or "zh"
        result = qa.answer(query, lang)
        return ChatResponse(
            query=result["query"],
            answer=result["answer"],
            confidence=float(result.get("confidence", 0)),
            sources=result.get("sources", []),
            intent=intent,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/stt")
async def speech_to_text(audio: UploadFile = File(...), lang: Optional[str] = "zh"):
    """语音转文字接口 - 接收音频文件，返回识别的文字"""
    if not _stt_available:
        raise HTTPException(
            status_code=501,
            detail="语音识别服务未安装，请在服务端安装 speech_recognition 库：pip install SpeechRecognition",
        )

    # 保存上传的音频到临时文件
    suffix = ".webm"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        content = await audio.read()
        tmp.write(content)
        tmp.close()

        recognizer = sr.Recognizer()

        # 使用 pydub 将 webm 转换为 wav（speech_recognition 需要 wav 格式）
        try:
            from pydub import AudioSegment

            audio_segment = AudioSegment.from_file(tmp.name)
            wav_path = tmp.name.replace(suffix, ".wav")
            audio_segment.export(wav_path, format="wav")
        except ImportError:
            # 如果没有 pydub，尝试直接用（可能不支持 webm）
            wav_path = tmp.name
        except Exception:
            wav_path = tmp.name

        try:
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)

            # 使用 Google 免费语音识别 API（支持多语言）
            stt_lang = "en-US" if lang == "en" else "zh-CN"
            text = recognizer.recognize_google(audio_data, language=stt_lang)
            return {"text": text}
        except sr.UnknownValueError:
            return {"text": "", "message": "未识别到有效语音"}
        except sr.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"语音识别服务不可用: {str(e)}。请检查网络连接。",
            )
        finally:
            # 清理临时文件
            try:
                os.unlink(tmp.name)
                if wav_path != tmp.name and os.path.exists(wav_path):
                    os.unlink(wav_path)
            except Exception:
                pass
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"语音识别处理失败: {str(exc)}")


if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_server:app", host="0.0.0.0", port=8080, reload=False)

# 浏览器中打开http://localhost:8080/
