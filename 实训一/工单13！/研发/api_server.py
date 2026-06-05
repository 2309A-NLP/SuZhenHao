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
from fastapi.responses import FileResponse, StreamingResponse
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
from image_processor import ImageProcessor, save_uploaded_image, get_image_info
from config import PDF_DIR, SUPPORTED_IMAGE_FORMATS, MAX_IMAGE_SIZE_MB, IMAGE_DIR
from redis_cache import (
    check_redis, get_query_cache, set_query_cache, clear_query_cache,
    get_session, save_session, delete_session, list_sessions,
    create_task, update_task, get_task,
)
import uuid
import time as _time

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


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str = ""


class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    lang: str = Field(default="zh", pattern="^(zh|en)$")
    history: Optional[List[ChatMessage]] = None  # 多轮对话历史
    retrieval_mode: Optional[str] = None  # 检索模式：vector / bm25 / hybrid


class ChatResponse(BaseModel):
    query: str
    answer: str
    confidence: float
    sources: list
    intent: Optional[str] = None
    image_analysis: Optional[str] = None  # 图片分析结果
    retrieval_time: Optional[float] = None  # 检索耗时（秒）


class ImageChatRequest(BaseModel):
    query: Optional[str] = Field(default=None, max_length=2000)
    lang: str = Field(default="zh", pattern="^(zh|en)$")


class SetActivePDFsRequest(BaseModel):
    pdf_names: Optional[List[str]] = None  # None = 全部激活


class RetrievalModeRequest(BaseModel):
    mode: str = Field(..., pattern="^(vector|bm25|hybrid|lightrag)$")


@app.on_event("startup")
def warmup():
    """启动时预加载模型与索引"""
    try:
        from config import RETRIEVAL_MODE
        get_qa_system(retrieval_mode=RETRIEVAL_MODE)
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


# ── 检索模式接口 ────────────────────────────────────────────

@app.get("/api/retrieval-mode")
async def get_retrieval_mode():
    """获取当前检索模式。"""
    from config import RETRIEVAL_MODE
    qa = get_qa_system()
    current_mode = "unknown"
    if hasattr(qa.retriever, 'retrieval_mode'):
        current_mode = qa.retriever.retrieval_mode
    return {
        "current_mode": current_mode,
        "default_mode": RETRIEVAL_MODE,
        "available_modes": ["vector", "bm25", "hybrid", "lightrag"],
    }


@app.post("/api/retrieval-mode")
async def set_retrieval_mode(body: RetrievalModeRequest):
    """切换检索模式，索引存在则直接加载，不存在则重建。"""
    try:
        qa = get_qa_system(force_rebuild=False, retrieval_mode=body.mode)
        return {
            "status": "ok",
            "mode": body.mode,
            "message": f"已切换到 {body.mode} 检索模式",
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"切换检索模式失败: {str(exc)}")


# ── 聊天接口 ────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest):
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="问题不能为空")

    try:
        retrieval_mode = getattr(body, 'retrieval_mode', None)
        mode = retrieval_mode or "hybrid"

        # 查询缓存
        cached = get_query_cache(query, mode)
        if cached:
            print(f"[缓存命中] {query[:30]}...")
            return ChatResponse(**cached)

        qa = get_qa_system()
        intent = None
        if qa.query_processor:
            processed = qa.query_processor.process_query(query)
            intent = processed.get("intent")

        lang = getattr(body, 'lang', 'zh') or "zh"
        # 构建历史消息列表
        history = None
        if body.history:
            history = [{"role": msg.role, "content": msg.content} for msg in body.history]
        qa = get_qa_system(retrieval_mode=retrieval_mode)
        result = qa.answer(query, lang, history=history)

        response_data = {
            "query": result["query"],
            "answer": result["answer"],
            "confidence": float(result.get("confidence", 0)),
            "sources": result.get("sources", []),
            "intent": intent,
            "retrieval_time": result.get("retrieval_time"),
        }

        # 写入缓存
        set_query_cache(query, mode, response_data)

        return ChatResponse(**response_data)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/chat/stream")
async def chat_stream(body: ChatRequest):
    """流式问答接口 - 使用 SSE (Server-Sent Events) 逐步返回答案。"""
    query = body.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="问题不能为空")

    try:
        lang = getattr(body, 'lang', 'zh') or "zh"
        history = None
        if body.history:
            history = [{"role": msg.role, "content": msg.content} for msg in body.history]
        retrieval_mode = getattr(body, 'retrieval_mode', None)
        qa = get_qa_system(retrieval_mode=retrieval_mode)

        metadata, content_gen = qa.answer_stream(query, lang, history=history)

        def event_stream():
            import json
            # 先发送元数据（sources, confidence 等）
            meta_event = {
                "type": "metadata",
                "query": metadata.get("query", query),
                "sources": metadata.get("sources", []),
                "confidence": metadata.get("confidence", 0),
                "retrieval_time": metadata.get("retrieval_time"),
            }
            yield f"data: {json.dumps(meta_event, ensure_ascii=False)}\n\n"

            # 逐块发送内容
            for chunk in content_gen:
                content_event = {
                    "type": "content",
                    "content": chunk,
                }
                yield f"data: {json.dumps(content_event, ensure_ascii=False)}\n\n"

            # 发送结束标记
            yield f"data: {json.dumps({'type': 'done'})}\n\n"

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ── 图片处理接口 ────────────────────────────────────────────

image_processor = ImageProcessor()


@app.get("/api/image-status")
async def image_status():
    """检查图片处理服务状态。"""
    return {
        "available": image_processor.available,
        "model": image_processor.model if image_processor.available else None,
    }


@app.post("/api/analyze-image")
async def analyze_image(
    file: UploadFile = File(...),
    question: Optional[str] = None,
    lang: Optional[str] = "zh",
):
    """上传图片并进行分析。"""
    if not image_processor.available:
        raise HTTPException(
            status_code=501,
            detail="图片处理服务未配置，请在 .env 文件中配置 QWEN_VL_API_KEY",
        )

    # 验证文件格式
    if not any(file.filename.lower().endswith(ext) for ext in SUPPORTED_IMAGE_FORMATS):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式，支持: {', '.join(SUPPORTED_IMAGE_FORMATS)}",
        )

    try:
        content = await file.read()

        # 验证文件大小
        size_mb = len(content) / (1024 * 1024)
        if size_mb > MAX_IMAGE_SIZE_MB:
            raise HTTPException(
                status_code=400,
                detail=f"图片文件过大: {size_mb:.1f}MB，最大支持 {MAX_IMAGE_SIZE_MB}MB",
            )

        # 保存图片
        save_path = save_uploaded_image(content, file.filename)
        image_url = "/api/images/" + os.path.basename(save_path)

        # 分析图片
        result = image_processor.analyze_image(
            save_path,
            question=question,
            lang=lang or "zh",
        )
        result["image_url"] = image_url

        return result

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"图片分析失败: {str(exc)}")


@app.post("/api/image-chat")
async def image_chat(
    file: UploadFile = File(...),
    query: Optional[str] = None,
    lang: Optional[str] = "zh",
):
    """图片问答接口 - 上传图片并结合文档进行问答。"""
    if not image_processor.available:
        raise HTTPException(
            status_code=501,
            detail="图片处理服务未配置，请在 .env 文件中配置 QWEN_VL_API_KEY",
        )

    # 验证文件格式
    if not any(file.filename.lower().endswith(ext) for ext in SUPPORTED_IMAGE_FORMATS):
        raise HTTPException(
            status_code=400,
            detail=f"不支持的图片格式，支持: {', '.join(SUPPORTED_IMAGE_FORMATS)}",
        )

    try:
        content = await file.read()

        # 验证文件大小
        size_mb = len(content) / (1024 * 1024)
        if size_mb > MAX_IMAGE_SIZE_MB:
            raise HTTPException(
                status_code=400,
                detail=f"图片文件过大: {size_mb:.1f}MB，最大支持 {MAX_IMAGE_SIZE_MB}MB",
            )

        # 保存图片
        save_path = save_uploaded_image(content, file.filename)
        image_url = "/api/images/" + os.path.basename(save_path)

        # 1. 先用 Qwen-VL 分析图片
        image_result = image_processor.analyze_image(
            save_path,
            question=query,
            lang=lang or "zh",
        )
        image_result["image_url"] = image_url

        # 2. 如果有 query，结合文档进行 RAG 问答
        qa_result = None
        if query:
            try:
                qa = get_qa_system()
                # 将图片分析结果作为额外上下文
                enhanced_query = f"{query}\n\n[图片分析结果]\n{image_result['analysis']}"
                qa_result = qa.answer(enhanced_query, lang or "zh")
            except Exception as e:
                print(f"[警告] RAG 问答失败: {e}")

        return {
            "image_analysis": image_result,
            "qa_result": qa_result,
        }

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"图片问答失败: {str(exc)}")


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


# ── 评估结果接口 ────────────────────────────────────────────

@app.get("/api/eval-results")
async def get_eval_results():
    """获取 RAGAS 评估结果。"""
    import json as _json
    results_path = ROOT / "eval" / "eval_results.json"
    if not results_path.exists():
        return {"status": "not_found", "message": "评估结果不存在，请先运行评估脚本: python eval/ragas_eval.py"}
    with open(results_path, "r", encoding="utf-8") as f:
        return _json.load(f)


@app.get("/api/comparison-table")
async def get_comparison_table():
    """获取对比表格数据。"""
    import json as _json
    table_path = ROOT / "eval" / "comparison_table.json"
    if not table_path.exists():
        return {"status": "not_found", "message": "对比数据不存在，请先运行评估脚本"}
    with open(table_path, "r", encoding="utf-8") as f:
        return _json.load(f)


@app.get("/eval.html")
async def eval_page():
    """评估结果展示页面。"""
    eval_html = FRONTEND / "eval.html"
    if not eval_html.exists():
        raise HTTPException(status_code=404, detail="评估页面不存在")
    return FileResponse(eval_html)


# ── Redis 健康检查 ──────────────────────────────────────────

@app.get("/api/redis-status")
async def redis_status():
    """检查 Redis 连接状态。"""
    ok = check_redis()
    return {"status": "ok" if ok else "unavailable", "connected": ok}


# ── 会话管理 API ─────────────────────────────────────────

class SessionRequest(BaseModel):
    chat_id: Optional[str] = None
    messages: List[dict] = []


@app.post("/api/sessions")
async def api_save_session(body: SessionRequest):
    """保存会话。"""
    try:
        chat_id = body.chat_id or str(uuid.uuid4())
        save_session(chat_id, body.messages)
        return {"status": "ok", "chat_id": chat_id}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/sessions")
async def api_list_sessions():
    """获取会话列表。"""
    try:
        sessions = list_sessions()
        return {"sessions": sessions}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/sessions/{chat_id}")
async def api_get_session(chat_id: str):
    """获取单个会话。"""
    try:
        messages = get_session(chat_id)
        return {"chat_id": chat_id, "messages": messages}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/api/sessions/{chat_id}")
async def api_delete_session(chat_id: str):
    """删除会话。"""
    try:
        delete_session(chat_id)
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/api/sessions")
async def api_clear_sessions():
    """清空所有会话。"""
    try:
        from redis_cache import get_redis_client
        r = get_redis_client()
        keys = r.keys("session:*")
        if keys:
            r.delete(*keys)
        r.delete("sessions:index")
        return {"status": "ok"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── 任务队列 API ─────────────────────────────────────────

@app.post("/api/tasks")
async def api_create_task(body: dict):
    """创建异步任务。"""
    try:
        task_id = str(uuid.uuid4())[:8]
        task_type = body.get("type", "unknown")
        task = create_task(task_id, task_type, body.get("params"))
        return task
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/tasks/{task_id}")
async def api_get_task(task_id: str):
    """查询任务状态。"""
    try:
        task = get_task(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        return task
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.delete("/api/cache")
async def api_clear_cache():
    """清空查询缓存。"""
    try:
        clear_query_cache()
        return {"status": "ok", "message": "查询缓存已清空"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


if FRONTEND.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND / "static"), name="static")

# 图片静态文件服务
images_dir = Path(IMAGE_DIR)
images_dir.mkdir(parents=True, exist_ok=True)
app.mount("/api/images", StaticFiles(directory=str(images_dir)), name="images")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api_server:app", host="0.0.0.0", port=8080, reload=False)
print("请在浏览器打开: http://localhost:8080")