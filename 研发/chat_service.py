# 核心对话服务 MultiRoleChatService：
# 编排 RAG 检索、记忆读写、调用大模型、存储对话。

import os
import time
from typing import Any, Dict, Generator, Tuple

import openai
from pymilvus import MilvusClient

from short_term_memory import ShortTermMemory
from mysql_store import MySQLStore
from prompts import build_user_message, get_system_prompt
from role_config import get_role_config

# ================== 修改点 1：环境变量改为 vLLM 相关 ==================
# 原 DeepSeek 配置（已注释，保留备用）
# DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "sk-840d940fbe6647109da000608d2")
# DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
# DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

# 新的 vLLM 本地服务配置（默认端口 8000，API Key 可为空字符串或 "EMPTY"）
VLLM_BASE_URL = os.getenv("VLLM_BASE_URL", "http://localhost:8000/v1")
VLLM_API_KEY = os.getenv("VLLM_API_KEY", "EMPTY")
VLLM_MODEL_NAME = os.getenv("VLLM_MODEL_NAME", "Qwen/Qwen3-0.6B")

# Milvus 配置保持不变
MILVUS_URI = os.getenv("MILVUS_URI", "http://192.168.253.131:19530")


class MultiRoleChatService:
    def __init__(self):
        self.stm = ShortTermMemory()
        self.mysql = MySQLStore()

        # ================== 修改点 2：初始化 OpenAI 客户端指向本地 vLLM ==================
        # 原来：self.llm_client = openai.OpenAI(base_url=DEEPSEEK_BASE_URL, api_key=DEEPSEEK_API_KEY)
        self.llm_client = openai.OpenAI(
            base_url=VLLM_BASE_URL,
            api_key=VLLM_API_KEY,
        )
        # 模型名称使用 vLLM 中注册的名称
        self.model_name = VLLM_MODEL_NAME

        # 其余原有属性保持不变
        self._conv_client = None
        self._conv_client_failed = False
        self.conv_collection = "conversation_history"
        self._conv_fields_cache = None
        self._retriever_cache: Dict[str, Any] = {}
        self._ltm_cache: Dict[str, Any] = {}

    def _get_conv_client(self):
        if self._conv_client_failed:
            return None
        if self._conv_client is not None:
            return self._conv_client
        try:
            self._conv_client = MilvusClient(uri=MILVUS_URI, timeout=5.0)
        except TypeError:
            self._conv_client = MilvusClient(uri=MILVUS_URI)
        except Exception as e:
            print(f"[Milvus] conversation_history 不可用（已跳过向量日志）: {e}")
            self._conv_client_failed = True
            return None
        return self._conv_client

    def _get_conversation_collection_fields(self):
        if self._conv_fields_cache is not None:
            return self._conv_fields_cache
        client = self._get_conv_client()
        if client is None:
            self._conv_fields_cache = set()
            return self._conv_fields_cache
        try:
            info = client.describe_collection(self.conv_collection)
            fields = set()
            for field in info.get("fields", []):
                name = field.get("name")
                if name:
                    fields.add(name)
            self._conv_fields_cache = fields
            return fields
        except Exception:
            self._conv_fields_cache = set()
            return self._conv_fields_cache

    def _get_retriever(self, role_code: str):
        from rag_retriever import RoleRetriever

        if role_code not in self._retriever_cache:
            self._retriever_cache[role_code] = RoleRetriever(role_code)
        return self._retriever_cache[role_code]

    def _safe_get_ltm(self, role_code: str):
        if role_code in self._ltm_cache:
            return self._ltm_cache[role_code]
        try:
            from memory import LongTermMemory
            ltm = LongTermMemory(role_code)
            self._ltm_cache[role_code] = ltm
            return ltm
        except Exception as e:
            print(f"[LTM] 初始化失败，已跳过长期记忆: {e}")
            self._ltm_cache[role_code] = None
            return None

    # ================== 修改点 3：_call_llm 和 _stream_llm 中移除 API Key 校验 ==================
    # 因为本地 vLLM 服务不强制要求 API Key，只要客户端能连接即可。
    # 原代码中检查 DEEPSEEK_API_KEY 的逻辑可以注释或修改为检查 VLLM_BASE_URL。
    def _call_llm(self, messages):
        # 原校验：if not DEEPSEEK_API_KEY: ...
        # 改为检查 base_url 是否为空（理论上不会为空）
        if not VLLM_BASE_URL:
            return "系统未配置 VLLM_BASE_URL，请先配置环境变量后再提问。"
        try:
            response = self.llm_client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.72,
                max_tokens=512,
                top_p=0.9,
                frequency_penalty=0.2,
                presence_penalty=0.2,
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"抱歉，我现在无法回答您的问题（API 错误：{str(e)}）。请稍后再试。"

    def _stream_llm(self, messages) -> Generator[str, None, None]:
        if not VLLM_BASE_URL:
            yield "系统未配置 VLLM_BASE_URL，请先配置环境变量后再提问。"
            return
        try:
            stream = self.llm_client.chat.completions.create(
                model=self.model_name,
                messages=messages,
                temperature=0.72,
                max_tokens=512,
                top_p=0.9,
                frequency_penalty=0.2,
                presence_penalty=0.2,
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                content = getattr(delta, "content", None)
                if content:
                    yield content
        except Exception as e:
            yield f"抱歉，我现在无法回答您的问题（API 错误：{str(e)}）。请稍后再试。"

    # 以下方法无需修改，保持原样
    def _build_recent_dialogue_context(self, role_code: str, history: list, max_rounds: int = 4) -> str:
        role_meta = get_role_config(role_code)
        if not history:
            return ""
        recent = history[-(max_rounds * 2):]
        lines = []
        for turn in recent:
            speaker = "用户" if turn.get("role") == "user" else role_meta["display_name"]
            content = (turn.get("content") or "").strip()
            if content:
                lines.append(f"{speaker}: {content}")
        return "\n".join(lines)

    def _build_messages(self, user_id: str, role_code: str, message: str, session_id: str) -> Tuple[list, list]:
        role_meta = get_role_config(role_code)
        self.stm.ensure_session(user_id, role_code, session_id)
        history = self.stm.get_history(user_id, role_code, session_id)
        if not history:
            try:
                warm = self.mysql.get_history(user_id, role_code, session_id, limit=20)
                for turn in warm[-20:]:
                    self.stm.add_message(
                        user_id,
                        role_code,
                        session_id,
                        turn.get("role", "user"),
                        turn.get("content", ""),
                    )
                history = self.stm.get_history(user_id, role_code, session_id)
            except Exception as e:
                print(f"[MySQL] 预热历史失败: {e}")

        sources = []
        retrieved_context = "暂无可用专业参考内容。"
        try:
            retriever = self._get_retriever(role_code)
            sources = retriever.hybrid_search(message, top_k=3)
            retrieved_context = retriever.format_docs_as_context(sources)
            if retriever.client is None and role_code not in self._ltm_cache:
                self._ltm_cache[role_code] = None
                print("[LTM] Milvus 不可用，已跳过长期记忆（与 RAG 使用同一服务）。")
        except Exception as e:
            print(f"[RAG] 检索失败，继续无知识库对话: {e}")

        ltm = self._safe_get_ltm(role_code)
        long_memories = []
        if ltm is not None:
            try:
                long_memories = ltm.retrieve_memories(user_id, message, top_k=3)
            except Exception as e:
                print(f"[LTM] 检索长期记忆失败: {e}")
        history_context = self._build_recent_dialogue_context(role_code, history, max_rounds=4)
        extra_memories = [f"最近会话摘要:\n{history_context}"] if history_context else []
        if long_memories:
            extra_memories.append("历史偏好与长期信息:\n" + "\n".join(f"- {item}" for item in long_memories))

        messages = [{"role": "system", "content": get_system_prompt(role_code)}]
        for turn in history[-8:]:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({
            "role": "user",
            "content": build_user_message(message, retrieved_context, extra_memories, role_meta),
        })
        return messages, sources

    def _persist_chat_result(self, user_id: str, role_code: str, session_id: str, message: str, answer: str,
                             sources: list):
        role_meta = get_role_config(role_code)
        now_ts = int(time.time())
        title = (message or "新对话").strip()[:24]

        self.stm.add_message(user_id, role_code, session_id, "user", message)
        self.stm.add_message(user_id, role_code, session_id, "assistant", answer)
        try:
            self.mysql.ensure_user(user_id, display_name=user_id)
            self.mysql.ensure_session(user_id, role_code, session_id, title=title, last_message=message)
            self.mysql.insert_message(user_id, role_code, session_id, "user", message, timestamp=now_ts,
                                      sources=sources)
            self.mysql.insert_message(user_id, role_code, session_id, "assistant", answer, timestamp=now_ts,
                                      sources=sources)
            self.mysql.update_session_title(user_id, role_code, session_id, title)
        except Exception as e:
            print(f"[MySQL] 存储对话失败: {e}")

        try:
            ltm = self._safe_get_ltm(role_code)
            if ltm is not None:
                ltm.add_memory(user_id, f"用户问题：{message}", memory_type="dialogue", importance=0.5)
                ltm.add_memory(user_id, f"{role_meta['display_name']}回复：{answer}", memory_type="dialogue",
                               importance=0.6)
        except Exception as e:
            print(f"存储长期记忆失败: {e}")

        data = {
            "user_id": user_id,
            "role_code": role_code,
            "session_id": session_id,
            "user_message": message,
            "assistant_response": answer,
            "timestamp": now_ts,
            "retrieved_sources": str([s.get("title", "") for s in sources])[:4000],
            "dummy_vector": [0.0, 0.0],
        }
        conv_client = self._get_conv_client()
        if conv_client is None:
            return
        try:
            if conv_client.has_collection(self.conv_collection):
                allowed_fields = self._get_conversation_collection_fields()
                if allowed_fields:
                    data = {k: v for k, v in data.items() if k in allowed_fields}
                conv_client.insert(self.conv_collection, data)
        except Exception as e:
            print(f"存储对话记录失败: {e}")

    def stream_chat(self, user_id: str, role_code: str, message: str, session_id: str = "default") -> Generator[
        Dict, None, None]:
        messages, sources = self._build_messages(user_id, role_code, message, session_id)
        answer_parts = []
        role_meta = get_role_config(role_code)
        for chunk in self._stream_llm(messages):
            answer_parts.append(chunk)
            yield {"type": "chunk", "content": chunk, "role_code": role_code}

        answer = "".join(answer_parts).strip()
        if not answer:
            answer = f"抱歉，{role_meta['display_name']}这次没有生成有效回答。"
            yield {"type": "chunk", "content": answer, "role_code": role_code}
        self._persist_chat_result(user_id, role_code, session_id, message, answer, sources)
        yield {"type": "done", "sources": sources, "role_code": role_code}

    def get_user_history(self, user_id: str, role_code: str, session_id: str = "default") -> list:
        try:
            return self.mysql.get_history(user_id, role_code, session_id, limit=200)
        except Exception as e:
            print(f"[MySQL] 读取历史失败，回退短期记忆: {e}")
            return self.stm.get_history(user_id, role_code, session_id)

    def clear_user_history(self, user_id: str, role_code: str, session_id: str = "default") -> None:
        self.stm.clear_session(user_id, role_code, session_id)
        try:
            self.mysql.clear_session(user_id, role_code, session_id)
        except Exception as e:
            print(f"[MySQL] 清空会话失败: {e}")

    def delete_user_session(self, user_id: str, role_code: str, session_id: str = "default") -> None:
        self.stm.clear_session(user_id, role_code, session_id)
        try:
            self.mysql.delete_session(user_id, role_code, session_id)
        except Exception as e:
            print(f"[MySQL] 删除会话失败: {e}")

    def list_user_sessions(self, user_id: str, role_code: str) -> list:
        try:
            return self.mysql.list_sessions(user_id, role_code)
        except Exception as e:
            print(f"[MySQL] 列会话失败，回退短期记忆: {e}")
            session_ids = self.stm.list_sessions(user_id, role_code)
            return [{"session_id": sid, "title": sid, "last_message": "", "updated_at": int(time.time())} for sid in
                    session_ids]

    def create_user_session(self, user_id: str, role_code: str, session_id: str) -> None:
        self.stm.ensure_session(user_id, role_code, session_id)
        try:
            self.mysql.ensure_user(user_id, display_name=user_id)
            self.mysql.ensure_session(user_id, role_code, session_id, title="新对话")
        except Exception as e:
            print(f"[MySQL] 创建会话失败: {e}")
