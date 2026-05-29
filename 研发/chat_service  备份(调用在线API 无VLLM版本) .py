# -*- coding: utf-8 -*-
# 调用在线API 无VLLM版本
# 核心对话服务 MultiRoleChatService：
# 编排 RAG 检索、记忆读写、调用大模型、存储对话。


# 导入操作系统相关模块，用于读取环境变量
import os
# 导入时间模块，用于生成时间戳
import time
# 导入类型注解工具，定义函数参数、返回值类型和生成器类型
from typing import Any, Dict, Generator, Tuple

# 导入OpenAI官方SDK，用于调用大模型API
import openai
# 导入Milvus向量数据库客户端，用于存储/检索向量数据
from pymilvus import MilvusClient

# 导入短期记忆管理类，管理内存中的对话历史
from short_term_memory import ShortTermMemory
# 导入MySQL存储类，管理持久化的对话数据
from mysql_store import MySQLStore
# 导入提示词构建工具，生成用户消息和系统提示词
from prompts import build_user_message, get_system_prompt
# 导入角色配置工具，获取不同AI角色的配置信息
from role_config import get_role_config

# 从环境变量读取DeepSeek大模型API密钥，无环境变量则使用默认值
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-840d940fbe6647109da000608d2a")
# 从环境变量读取DeepSeek API基础地址，无环境变量则使用默认值
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
# 从环境变量读取DeepSeek模型名称，无环境变量则使用默认值
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
# 从环境变量读取Milvus服务地址，无环境变量则使用默认值
MILVUS_URI = os.getenv("MILVUS_URI", "http://192.168.253.131:19530")


# 多角色对话服务核心类
class MultiRoleChatService:
    # 类初始化方法，创建服务实例时执行
    def __init__(self):
        # 初始化短期记忆实例，用于内存缓存对话
        self.stm = ShortTermMemory()
        # 初始化MySQL存储实例，用于持久化对话数据
        self.mysql = MySQLStore()
        # 初始化OpenAI兼容的大模型客户端（适配DeepSeek API）
        self.llm_client = openai.OpenAI(base_url=DEEPSEEK_BASE_URL, api_key=DEEPSEEK_API_KEY)
        # 存储大模型名称
        self.model_name = DEEPSEEK_MODEL
        # Milvus对话历史客户端，初始化为空
        self._conv_client = None
        # Milvus连接失败标记，初始为False
        self._conv_client_failed = False
        # Milvus中存储对话历史的集合名称
        self.conv_collection = "conversation_history"
        # 缓存Milvus集合字段，避免重复查询
        self._conv_fields_cache = None
        # 检索器缓存字典，键：角色编码，值：检索器实例
        self._retriever_cache: Dict[str, Any] = {}
        # 长期记忆缓存字典，键：角色编码，值：长期记忆实例
        self._ltm_cache: Dict[str, Any] = {}

    # 获取Milvus对话历史客户端（单例模式，避免重复创建）
    def _get_conv_client(self):
        # 如果之前连接失败，直接返回None，不再重试
        if self._conv_client_failed:
            return None
        # 如果客户端已创建，直接返回
        if self._conv_client is not None:
            return self._conv_client
        try:
            # 尝试创建带超时时间的Milvus客户端
            self._conv_client = MilvusClient(uri=MILVUS_URI, timeout=5.0)
        except TypeError:
            # 捕获版本不兼容错误，创建无超时参数的客户端
            self._conv_client = MilvusClient(uri=MILVUS_URI)
        except Exception as e:
            # 捕获所有异常，标记连接失败，打印错误信息
            print(f"[Milvus] conversation_history 不可用（已跳过向量日志）: {e}")
            self._conv_client_failed = True
            return None
        # 返回创建好的客户端
        return self._conv_client

    # 获取Milvus对话集合的所有字段（用于数据校验）
    def _get_conversation_collection_fields(self):
        # 如果缓存已存在，直接返回
        if self._conv_fields_cache is not None:
            return self._conv_fields_cache
        # 获取Milvus客户端
        client = self._get_conv_client()
        # 客户端为空时，缓存空集合并返回
        if client is None:
            self._conv_fields_cache = set()
            return self._conv_fields_cache
        try:
            # 查询集合详情
            info = client.describe_collection(self.conv_collection)
            # 初始化字段集合
            fields = set()
            # 遍历所有字段，提取字段名
            for field in info.get("fields", []):
                name = field.get("name")
                if name:
                    fields.add(name)
            # 缓存字段集合
            self._conv_fields_cache = fields
            return fields
        except Exception:
            # 异常时缓存空集合
            self._conv_fields_cache = set()
            return self._conv_fields_cache

    # 获取指定角色的RAG检索器（懒加载+缓存）
    def _get_retriever(self, role_code: str):
        # 内部导入，避免循环依赖
        from rag_retriever import RoleRetriever

        # 缓存中无该角色检索器时，创建新实例
        if role_code not in self._retriever_cache:
            self._retriever_cache[role_code] = RoleRetriever(role_code)
        # 返回检索器实例
        return self._retriever_cache[role_code]

    # 安全获取长期记忆实例（捕获异常，避免服务崩溃）
    def _safe_get_ltm(self, role_code: str):
        # 缓存中存在则直接返回
        if role_code in self._ltm_cache:
            return self._ltm_cache[role_code]
        try:
            # 内部导入，避免循环依赖
            from memory import LongTermMemory
            # 创建长期记忆实例
            ltm = LongTermMemory(role_code)
            # 存入缓存
            self._ltm_cache[role_code] = ltm
            return ltm
        except Exception as e:
            # 初始化失败，打印错误，缓存为空
            print(f"[LTM] 初始化失败，已跳过长期记忆: {e}")
            self._ltm_cache[role_code] = None
            return None

    # 调用大模型生成回答（非流式）
    def _call_llm(self, messages):
        # 无API密钥时，返回提示信息
        if not DEEPSEEK_API_KEY:
            return "系统未配置 DEEPSEEK_API_KEY，请先配置环境变量后再提问。"
        try:
            # 调用大模型聊天接口
            response = self.llm_client.chat.completions.create(
                model=self.model_name,       # 模型名称
                messages=messages,           # 对话消息列表
                temperature=0.72,            # 温度系数，控制随机性
                max_tokens=1024,             # 最大生成token数
                top_p=0.9,                   # 核采样参数
                frequency_penalty=0.2,       # 频率惩罚，减少重复
                presence_penalty=0.2,        # 存在惩罚，鼓励新话题
            )
            # 返回模型生成的回答内容
            return response.choices[0].message.content
        except Exception as e:
            # 捕获API异常，返回友好提示
            return f"抱歉，我现在无法回答您的问题（API 错误：{str(e)}）。请稍后再试。"

    # 流式调用大模型（逐字返回，提升用户体验）
    def _stream_llm(self, messages) -> Generator[str, None, None]:
        # 无API密钥时，返回提示信息
        if not DEEPSEEK_API_KEY:
            yield "系统未配置 DEEPSEEK_API_KEY，请先配置环境变量后再提问。"
            return
        try:
            # 开启流式调用大模型
            stream = self.llm_client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.72,
                max_tokens=1024,
                top_p=0.9,
                frequency_penalty=0.2,
                presence_penalty=0.2,
                stream=True,  # 开启流式输出
            )
            # 遍历流式响应片段
            for chunk in stream:
                # 无内容时跳过
                if not chunk.choices:
                    continue
                # 获取响应增量内容
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                # 有内容则返回
                if content:
                    yield content
        except Exception as e:
            # 异常时返回错误提示
            yield f"抱歉，我现在无法回答您的问题（API 错误：{str(e)}）。请稍后再试。"

    # 构建最近对话上下文，用于给大模型提供历史参考
    def _build_recent_dialogue_context(self, role_code: str, history: list, max_rounds: int = 4) -> str:
        # 获取当前角色配置
        role_meta = get_role_config(role_code)
        # 无历史记录时返回空字符串
        if not history:
            return ""
        # 截取最近N轮对话（一轮=用户+助手）
        recent = history[-(max_rounds * 2):]
        # 初始化对话行列表
        lines = []
        # 遍历历史记录
        for turn in recent:
            # 判断说话人：用户/AI角色
            speaker = "用户" if turn.get("role") == "user" else role_meta["display_name"]
            # 获取对话内容，去除首尾空格
            content = (turn.get("content") or "").strip()
            # 内容非空时，添加到列表
            if content:
                lines.append(f"{speaker}: {content}")
        # 拼接为字符串返回
        return "\n".join(lines)

    # 构建大模型所需的消息列表（核心方法）
    def _build_messages(self, user_id: str, role_code: str, message: str, session_id: str) -> Tuple[list, list]:
        # 获取角色配置
        role_meta = get_role_config(role_code)
        # 确保会话存在（创建新会话）
        self.stm.ensure_session(user_id, role_code, session_id)
        # 从短期记忆获取对话历史
        history = self.stm.get_history(user_id, role_code, session_id)
        # 短期记忆无历史时，从MySQL预热历史数据
        if not history:
            try:
                # 从MySQL获取最近20条历史
                warm = self.mysql.get_history(user_id, role_code, session_id, limit=20)
                # 将历史记录写入短期记忆
                for turn in warm[-20:]:
                    self.stm.add_message(
                        user_id,
                        role_code,
                        session_id,
                        turn.get("role", "user"),
                        turn.get("content", ""),
                    )
                # 重新获取更新后的历史
                history = self.stm.get_history(user_id, role_code, session_id)
            except Exception as e:
                # 预热失败打印错误
                print(f"[MySQL] 预热历史失败: {e}")

        # 初始化知识库检索结果
        sources = []
        # 默认检索上下文
        retrieved_context = "暂无可用专业参考内容。"
        try:
            # 获取当前角色的检索器
            retriever = self._get_retriever(role_code)
            # 混合检索知识库（关键词+向量）
            sources = retriever.hybrid_search(message, top_k=3)
            # 格式化检索结果为上下文
            retrieved_context = retriever.format_docs_as_context(sources)
            # 检索器客户端为空且未缓存长期记忆时，禁用长期记忆
            if retriever.client is None and role_code not in self._ltm_cache:
                self._ltm_cache[role_code] = None
                print("[LTM] Milvus 不可用，已跳过长期记忆（与 RAG 使用同一服务）。")
        except Exception as e:
            # 检索失败打印错误，继续无知识库对话
            print(f"[RAG] 检索失败，继续无知识库对话: {e}")

        # 获取长期记忆实例
        ltm = self._safe_get_ltm(role_code)
        # 初始化长期记忆列表
        long_memories = []
        if ltm is not None:
            try:
                # 检索用户相关的长期记忆
                long_memories = ltm.retrieve_memories(user_id, message, top_k=3)
            except Exception as e:
                # 检索失败打印错误
                print(f"[LTM] 检索长期记忆失败: {e}")
        # 构建最近对话上下文
        history_context = self._build_recent_dialogue_context(role_code, history, max_rounds=4)
        # 初始化额外记忆列表
        extra_memories = [f"最近会话摘要:\n{history_context}"] if history_context else []
        # 有长期记忆时，添加到额外记忆
        if long_memories:
            extra_memories.append("历史偏好与长期信息:\n" + "\n".join(f"- {item}" for item in long_memories))

        # 构建大模型消息列表，首先添加系统提示词
        messages = [{"role": "system", "content": get_system_prompt(role_code)}]
        # 添加最近8条对话历史（限制上下文长度）
        for turn in history[-8:]:
            messages.append({"role": turn["role"], "content": turn["content"]})
        # 构建并添加用户最终消息（包含问题、知识库、记忆）
        messages.append({
            "role": "user",
            "content": build_user_message(message, retrieved_context, extra_memories, role_meta),
        })
        # 返回构建好的消息列表和检索结果
        return messages, sources

    # 持久化对话结果（内存+MySQL+Milvus+长期记忆）
    def _persist_chat_result(self, user_id: str, role_code: str, session_id: str, message: str, answer: str, sources: list):
        # 获取角色配置
        role_meta = get_role_config(role_code)
        # 获取当前时间戳
        now_ts = int(time.time())
        # 生成会话标题（截取用户问题前24字符）
        title = (message or "新对话").strip()[:24]

        # 将用户消息写入短期记忆
        self.stm.add_message(user_id, role_code, session_id, "user", message)
        # 将助手回答写入短期记忆
        self.stm.add_message(user_id, role_code, session_id, "assistant", answer)
        try:
            # 确保用户存在于MySQL
            self.mysql.ensure_user(user_id, display_name=user_id)
            # 确保会话存在于MySQL
            self.mysql.ensure_session(user_id, role_code, session_id, title=title, last_message=message)
            # 插入用户消息到MySQL
            self.mysql.insert_message(user_id, role_code, session_id, "user", message, timestamp=now_ts, sources=sources)
            # 插入助手回答到MySQL
            self.mysql.insert_message(user_id, role_code, session_id, "assistant", answer, timestamp=now_ts, sources=sources)
            # 更新会话标题
            self.mysql.update_session_title(user_id, role_code, session_id, title)
        except Exception as e:
            # MySQL存储失败打印错误
            print(f"[MySQL] 存储对话失败: {e}")

        try:
            # 获取长期记忆实例
            ltm = self._safe_get_ltm(role_code)
            if ltm is not None:
                # 存储用户问题到长期记忆
                ltm.add_memory(user_id, f"用户问题：{message}", memory_type="dialogue", importance=0.5)
                # 存储助手回答到长期记忆
                ltm.add_memory(user_id, f"{role_meta['display_name']}回复：{answer}", memory_type="dialogue", importance=0.6)
        except Exception as e:
            # 长期记忆存储失败打印错误
            print(f"存储长期记忆失败: {e}")

        # 构建Milvus存储数据
        data = {
            "user_id": user_id,
            "role_code": role_code,
            "session_id": session_id,
            "user_message": message,
            "assistant_response": answer,
            "timestamp": now_ts,
            "retrieved_sources": str([s.get("title", "") for s in sources])[:4000],
            "dummy_vector": [0.0, 0.0],  # 占位向量，满足Milvus格式要求
        }
        # 获取Milvus客户端
        conv_client = self._get_conv_client()
        if conv_client is None:
            return
        try:
            # 检查集合是否存在
            if conv_client.has_collection(self.conv_collection):
                # 过滤字段，只插入集合存在的字段
                allowed_fields = self._get_conversation_collection_fields()
                if allowed_fields:
                    data = {k: v for k, v in data.items() if k in allowed_fields}
                # 插入数据到Milvus
                conv_client.insert(self.conv_collection, data)
        except Exception as e:
            # Milvus存储失败打印错误
            print(f"存储对话记录失败: {e}")

    # 流式对话接口（对外提供服务的核心方法）
    def stream_chat(self, user_id: str, role_code: str, message: str, session_id: str = "default") -> Generator[Dict, None, None]:
        # 构建大模型消息列表
        messages, sources = self._build_messages(user_id, role_code, message, session_id)
        # 初始化回答片段列表
        answer_parts = []
        # 获取角色配置
        role_meta = get_role_config(role_code)
        # 遍历流式响应片段
        for chunk in self._stream_llm(messages):
            answer_parts.append(chunk)
            # yield返回片段数据，前端实时展示
            yield {"type": "chunk", "content": chunk, "role_code": role_code}

        # 拼接完整回答
        answer = "".join(answer_parts).strip()
        # 回答为空时，生成默认提示
        if not answer:
            answer = f"抱歉，{role_meta['display_name']}这次没有生成有效回答。"
            yield {"type": "chunk", "content": answer, "role_code": role_code}
        # 持久化对话结果
        self._persist_chat_result(user_id, role_code, session_id, message, answer, sources)
        # 返回完成信号和检索结果
        yield {"type": "done", "sources": sources, "role_code": role_code}

    # 获取用户对话历史
    def get_user_history(self, user_id: str, role_code: str, session_id: str = "default") -> list:
        try:
            # 优先从MySQL获取历史
            return self.mysql.get_history(user_id, role_code, session_id, limit=200)
        except Exception as e:
            # MySQL失败，回退到短期记忆
            print(f"[MySQL] 读取历史失败，回退短期记忆: {e}")
            return self.stm.get_history(user_id, role_code, session_id)

    # 清空用户指定会话历史
    def clear_user_history(self, user_id: str, role_code: str, session_id: str = "default") -> None:
        # 清空短期记忆
        self.stm.clear_session(user_id, role_code, session_id)
        try:
            # 清空MySQL会话数据
            self.mysql.clear_session(user_id, role_code, session_id)
        except Exception as e:
            print(f"[MySQL] 清空会话失败: {e}")

    # 删除用户指定会话
    def delete_user_session(self, user_id: str, role_code: str, session_id: str = "default") -> None:
        # 清空短期记忆
        self.stm.clear_session(user_id, role_code, session_id)
        try:
            # 删除MySQL会话数据
            self.mysql.delete_session(user_id, role_code, session_id)
        except Exception as e:
            print(f"[MySQL] 删除会话失败: {e}")

    # 列出用户所有会话
    def list_user_sessions(self, user_id: str, role_code: str) -> list:
        try:
            # 优先从MySQL获取会话列表
            return self.mysql.list_sessions(user_id, role_code)
        except Exception as e:
            # MySQL失败，回退到短期记忆
            print(f"[MySQL] 列会话失败，回退短期记忆: {e}")
            session_ids = self.stm.list_sessions(user_id, role_code)
            # 构造会话列表数据结构返回
            return [{"session_id": sid, "title": sid, "last_message": "", "updated_at": int(time.time())} for sid in session_ids]

    # 创建用户新会话
    def create_user_session(self, user_id: str, role_code: str, session_id: str) -> None:
        # 确保短期记忆会话存在
        self.stm.ensure_session(user_id, role_code, session_id)
        try:
            # 确保MySQL用户和会话存在
            self.mysql.ensure_user(user_id, display_name=user_id)
            self.mysql.ensure_session(user_id, role_code, session_id, title="新对话")
        except Exception as e:
            print(f"[MySQL] 创建会话失败: {e}")
