"""FastAPI 后端 - 为聊天前端提供问答接口，支持多 PDF 管理"""
import sys
import tempfile
import os
from pathlib import Path
from typing import List, Optional

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

from app_core import (
    get_doc_info,
    get_qa_system,
    get_all_pdfs_info,
    set_active_pdfs,
    rebuild_index,
    get_active_pdfs,
)
from document_loader import delete_pdf
from config import PDF_DIR

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


class SetActivePDFsRequest(BaseModel):
    pdf_names: Optional[List[str]] = None  # None = 全部激活


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


# ── PDF 管理接口 ────────────────────────────────────────────

@app.get("/api/pdfs")
async def list_pdfs():
    """获取所有 PDF 文件列表及激活状态。"""
    pdfs = get_all_pdfs_info()
    active = get_active_pdfs()
    return {
        "pdfs": pdfs,
        "active_pdfs": active,  # None 表示全部激活
        "total": len(pdfs),
    }


@app.post("/api/set-active-pdfs")
async def set_active(body: SetActivePDFsRequest):
    """设置激活的 PDF 文件列表，触发索引重建。"""
    pdf_names = body.pdf_names

    # 校验文件名是否存在
    if pdf_names is not None:
        existing = {p["name"] for p in get_all_pdfs_info()}
        for name in pdf_names:
            if name not in existing:
                raise HTTPException(status_code=400, detail=f"文件不存在: {name}")

    set_active_pdfs(pdf_names)

    # 后台重建索引
    try:
        rebuild_index()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"索引重建失败: {str(exc)}")

    return {
        "status": "ok",
        "active_pdfs": pdf_names,
        "message": "索引重建完成",
    }


@app.delete("/api/pdfs/{filename}")
async def remove_pdf(filename: str):
    """删除指定 PDF 文件并重建索引。"""
    success = delete_pdf(filename, PDF_DIR)
    if not success:
        raise HTTPException(status_code=404, detail=f"文件未找到: {filename}")

    # 如果删除的是当前激活的文件，清除激活列表
    active = get_active_pdfs()
    if active is not None and filename in active:
        new_active = [p for p in active if p != filename]
        set_active_pdfs(new_active if new_active else None)

    # 重建索引
    try:
        rebuild_index()
    except Exception as exc:
        return {
            "status": "ok",
            "message": f"文件已删除，但索引重建失败: {str(exc)}",
        }

    return {
        "status": "ok",
        "message": f"文件 {filename} 已删除，索引已更新",
    }


@app.post("/api/upload-pdf")
async def upload_pdf(file: UploadFile = File(...)):
    """接收前端上传的 PDF 文件，保存到 data 目录。"""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="仅支持 PDF 文件格式")

    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    save_path = data_dir / file.filename
    try:
        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)
        return {
            "status": "ok",
            "filename": file.filename,
            "size_mb": round(len(content) / (1024 * 1024), 2),
            "path": str(save_path),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"文件保存失败: {str(exc)}") from exc


@app.post("/api/rebuild-index")
async def api_rebuild_index():
    """手动触发索引重建。"""
    try:
        rebuild_index()
        return {"status": "ok", "message": "索引重建完成"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"索引重建失败: {str(exc)}")


# ── 聊天接口 ────────────────────────────────────────────────

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


# ── 语音识别接口 ────────────────────────────────────────────

@app.post("/api/stt")
async def speech_to_text(audio: UploadFile = File(...), lang: Optional[str] = "zh"):
    """语音转文字接口"""
    if not _stt_available:
        raise HTTPException(
            status_code=501,
            detail="语音识别服务未安装，请在服务端安装 speech_recognition 库",
        )

    suffix = ".webm"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        content = await audio.read()
        tmp.write(content)
        tmp.close()

        recognizer = sr.Recognizer()

        try:
            from pydub import AudioSegment
            audio_segment = AudioSegment.from_file(tmp.name)
            wav_path = tmp.name.replace(suffix, ".wav")
            audio_segment.export(wav_path, format="wav")
        except ImportError:
            wav_path = tmp.name
        except Exception:
            wav_path = tmp.name

        try:
            with sr.AudioFile(wav_path) as source:
                audio_data = recognizer.record(source)
            stt_lang = "en-US" if lang == "en" else "zh-CN"
            text = recognizer.recognize_google(audio_data, language=stt_lang)
            return {"text": text}
        except sr.UnknownValueError:
            return {"text": "", "message": "未识别到有效语音"}
        except sr.RequestError as e:
            raise HTTPException(status_code=503, detail=f"语音识别服务不可用: {str(e)}")
        finally:
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
