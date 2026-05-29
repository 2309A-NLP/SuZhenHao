# -*- coding: utf-8 -*-
# 指定文件编码为UTF-8，支持中文等多语言字符

# 导入FastAPI核心类，用于创建Web服务、接口定义
from fastapi import FastAPI, HTTPException, File, UploadFile, Form
# 导入FastAPI响应类：文件响应、流式响应（用于聊天流式输出）
from fastapi.responses import FileResponse, StreamingResponse
# 导入静态文件服务，用于托管前端页面
from fastapi.staticfiles import StaticFiles
# 导入Pydantic的BaseModel，用于定义请求/响应数据结构
from pydantic import BaseModel
# 导入类型注解：列表、可选类型
from typing import List, Optional
# 导入多角色对话核心服务类
from chat_service import MultiRoleChatService
# 导入角色配置：默认角色编码、角色列表函数
from role_config import DEFAULT_ROLE_CODE, list_roles
# 导入路径处理工具，用于文件路径操作
from pathlib import Path
# 导入JSON工具，用于数据序列化/反序列化
import json
# 导入ASGI服务器，用于运行FastAPI服务
import uvicorn
# 导入操作系统工具，用于文件删除、路径处理
import os
# 导入临时文件工具，用于处理上传的PDF文件
import tempfile

# 创建FastAPI应用实例，设置服务标题
app = FastAPI(title="多角色对话平台")
# 初始化多角色对话服务实例
chat_service = MultiRoleChatService()
# 获取当前代码文件所在的根目录
BASE_DIR = Path(__file__).resolve().parent
# 定义前端静态文件存放目录
FRONTEND_DIR = BASE_DIR / "frontend"

# 判断前端目录是否存在
if FRONTEND_DIR.exists():
    # 将静态文件目录挂载到 /static 路径，提供前端资源访问
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")


# 定义聊天请求数据模型
class ChatRequest(BaseModel):
    user_id: str  # 用户ID
    message: str  # 用户发送的消息
    role_code: str = DEFAULT_ROLE_CODE  # 角色编码，使用默认角色
    session_id: str = "default"  # 会话ID，默认会话


# 定义会话操作请求模型（创建/清空/删除会话）
class SessionRequest(BaseModel):
    user_id: str  # 用户ID
    role_code: str = DEFAULT_ROLE_CODE  # 角色编码
    session_id: str = "default"  # 会话ID


# 定义知识库构建请求模型（URL导入）
class KnowledgeBuildRequest(BaseModel):
    role_code: str  # 目标角色编码
    urls: List[str]  # 网页URL列表


# 定义消息条目模型，用于历史消息返回
class MessageItem(BaseModel):
    role: str  # 消息角色（user/assistant）
    content: str  # 消息内容
    timestamp: Optional[int] = None  # 时间戳，可选


# 定义引用来源模型，用于展示知识库引用片段
class Source(BaseModel):
    title: str  # 片段标题
    content: str  # 片段内容
    source: str  # 来源地址/文件
    score: float  # 相关性得分


# 定义聊天响应模型
class ChatResponse(BaseModel):
    response: str  # 机器人回复内容
    sources: List[Source] = []  # 引用的知识库片段


# 定义历史记录响应模型
class HistoryResponse(BaseModel):
    user_id: str  # 用户ID
    role_code: str  # 角色编码
    session_id: str  # 会话ID
    messages: List[MessageItem] = []  # 消息列表


# 定义会话条目模型
class SessionItem(BaseModel):
    session_id: str  # 会话ID
    title: str  # 会话标题
    last_message: str = ""  # 最后一条消息
    updated_at: Optional[int] = None  # 更新时间


# 定义会话列表响应模型
class SessionListResponse(BaseModel):
    user_id: str  # 用户ID
    role_code: str  # 角色编码
    sessions: List[SessionItem] = []  # 会话列表


# 定义PDF知识库构建响应模型
class PDFBuildResponse(BaseModel):
    ok: bool  # 是否成功
    role_code: str  # 角色编码
    collection_name: str  # Milvus集合名称
    source_count: int  # 数据源数量
    chunk_count: int  # 文本块数量
    sources: List[str]  # 数据源列表


# 定义聊天接口，POST请求 /api/chat
@app.post("/api/chat")
# 接收ChatRequest格式的请求体
async def chat(req: ChatRequest):
    try:
        # 初始化回复内容为空字符串
        response_text = ""
        # 初始化引用来源为空列表
        sources = []
        # 遍历流式聊天输出事件
        for event in chat_service.stream_chat(req.user_id, req.role_code, req.message, req.session_id):
            # 如果事件包含内容，拼接到回复
            if "content" in event:
                response_text += event["content"]
            # 如果事件包含来源，赋值给sources
            if "sources" in event:
                sources = event["sources"]

        # 返回成功结果
        return {
            "success": True,
            "response": response_text,
            "sources": sources
        }
    except Exception as e:
        # 捕获异常，返回错误信息
        return {
            "success": False,
            "response": f"抱歉，发生错误：{str(e)}",
            "sources": []
        }


# 定义获取聊天历史接口，GET请求 /api/history/{用户ID}/{角色}/{会话ID}
@app.get("/api/history/{user_id}/{role_code}/{session_id}", response_model=HistoryResponse)
async def history(user_id: str, role_code: str, session_id: str):
    try:
        # 调用服务获取历史消息
        messages = chat_service.get_user_history(user_id, role_code, session_id)
        # 返回标准化响应
        return HistoryResponse(user_id=user_id, role_code=role_code, session_id=session_id, messages=messages)
    except Exception as e:
        # 抛出500服务器异常
        raise HTTPException(status_code=500, detail=str(e))


# 定义获取用户会话列表接口
@app.get("/api/sessions")
async def sessions(user_id: str, role_code: str = DEFAULT_ROLE_CODE):
    try:
        # 获取会话列表
        sessions = chat_service.list_user_sessions(user_id, role_code)
        return sessions
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 定义获取所有角色列表接口
@app.get("/api/roles")
async def roles():
    return list_roles()


# 定义创建会话接口
@app.post("/api/create_session")
async def create_session(req: SessionRequest):
    try:
        # 调用服务创建用户会话
        chat_service.create_user_session(req.user_id, req.role_code, req.session_id)
        return {"ok": True, "user_id": req.user_id, "role_code": req.role_code, "session_id": req.session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 定义清空会话历史接口
@app.post("/api/clear_session")
async def clear_session(req: SessionRequest):
    try:
        # 清空指定会话历史
        chat_service.clear_user_history(req.user_id, req.role_code, req.session_id)
        return {"ok": True, "user_id": req.user_id, "role_code": req.role_code, "session_id": req.session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 定义删除会话接口
@app.post("/api/delete_session")
async def delete_session(req: SessionRequest):
    try:
        # 删除指定会话
        chat_service.delete_user_session(req.user_id, req.role_code, req.session_id)
        return {"ok": True, "user_id": req.user_id, "role_code": req.role_code, "session_id": req.session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 定义URL构建知识库接口
@app.post("/api/knowledge/build")
async def build_knowledge(req: KnowledgeBuildRequest):
    try:
        # 动态导入知识库构建函数
        from build_role_kb import build_role_knowledge_base
        # 执行构建
        result = build_role_knowledge_base(req.role_code, urls=req.urls)
        return {"ok": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 定义PDF上传构建知识库接口
@app.post("/api/knowledge/build_pdf")
async def build_knowledge_pdf(
        role_code: str = Form(...),  # 表单字段：角色编码
        files: List[UploadFile] = File(...),  # 上传文件列表
        parse_method: str = Form("auto"),  # 表单字段：PDF解析方式
):
    """
    通过PDF文件构建知识库

    Args:
        role_code: 目标角色编码
        files: 上传的PDF文件列表
        parse_method: 解析方法，可选值: auto, pymupdf, pdfplumber, mineru, paddleocr

    Returns:
        构建结果统计
    """
    # 判断是否上传文件
    if not files:
        raise HTTPException(status_code=400, detail="请至少上传一个PDF文件")

    # 定义合法的解析方法
    valid_methods = ["auto", "pymupdf", "pdfplumber", "mineru", "paddleocr"]
    # 校验解析方法是否合法
    if parse_method not in valid_methods:
        raise HTTPException(status_code=400, detail=f"无效的解析方法: {parse_method}，可选值: {valid_methods}")

    # 临时文件路径列表
    temp_files = []
    try:
        # 遍历上传的文件
        for file in files:
            # 判断文件是否为PDF
            if not file.filename.lower().endswith(".pdf"):
                raise HTTPException(status_code=400, detail=f"文件 {file.filename} 不是PDF文件")

            # 创建临时PDF文件
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                # 读取上传文件内容
                content = await file.read()
                # 写入临时文件
                temp_file.write(content)
                # 记录临时文件路径
                temp_files.append(temp_file.name)

        # 导入构建函数
        from build_role_kb import build_role_knowledge_base
        # 执行PDF知识库构建
        result = build_role_knowledge_base(
            role_code=role_code,
            pdf_files=temp_files,
            pdf_method=parse_method,
        )

        # 返回构建结果
        return {
            "success": True,
            "files_count": result.get("source_count", 0),
            "chunks_count": result.get("chunk_count", 0),
            "sources": result.get("sources", [])
        }

    # 捕获已知HTTP异常，直接抛出
    except HTTPException:
        raise
    # 捕获其他异常
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    # 最终执行：清理临时文件
    finally:
        for temp_file in temp_files:
            try:
                # 删除临时文件
                os.unlink(temp_file)
            except:
                # 删除失败则忽略
                pass


# 定义健康检查接口
@app.get("/api/health")
async def health():
    return {"status": "healthy"}


# 定义登录/注册请求模型
class AuthRequest(BaseModel):
    username: str  # 用户名
    password: str  # 密码


# 定义用户注册接口
@app.post("/api/auth/register")
async def register(req: AuthRequest):
    try:
        # 调用MySQL服务确保用户存在
        chat_service.mysql.ensure_user(req.username, req.username)
        return {"success": True, "message": "注册成功"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# 定义用户登录接口
@app.post("/api/auth/login")
async def login(req: AuthRequest):
    try:
        # 确保用户存在
        chat_service.mysql.ensure_user(req.username, req.username)
        return {"success": True, "message": "登录成功"}
    except Exception as e:
        return {"success": False, "message": str(e)}


# 定义退出登录接口
@app.post("/api/auth/logout")
async def logout():
    return {"success": True, "message": "退出成功"}


# 定义根路径，返回前端页面
@app.get("/")
async def index():
    # 前端首页文件路径
    index_file = FRONTEND_DIR / "index.html"
    # 判断文件是否存在
    if not index_file.exists():
        raise HTTPException(status_code=404, detail="前端页面不存在，请先创建 frontend/index.html")
    # 返回HTML文件
    return FileResponse(index_file)


# 主程序入口：直接运行时启动服务
if __name__ == "__main__":
    print("多角色对话平台已就绪（进程需保持运行以提供网页服务）。")
    print("请在浏览器打开: http://localhost:8080/")
    # 运行FastAPI服务，监听所有IP，端口8080
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="info")