"""
Redis 缓存模块 - 提供查询缓存、Embedding 缓存、会话管理、任务队列
"""
import json
import hashlib
import time
from typing import Any, Dict, List, Optional

import redis

from config import REDIS_HOST, REDIS_PORT, REDIS_DB, REDIS_PASSWORD, MAX_HISTORY, CACHE_TTL

# ── Redis 连接 ──────────────────────────────────────────────

def get_redis_client() -> redis.Redis:
    """获取 Redis 连接。"""
    return redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=REDIS_DB,
        password=REDIS_PASSWORD,
        decode_responses=True,
        socket_timeout=5,
        socket_connect_timeout=5,
    )


def check_redis() -> bool:
    """检查 Redis 是否可用。"""
    try:
        r = get_redis_client()
        r.ping()
        return True
    except Exception:
        return False


# ── 查询缓存 ──────────────────────────────────────────────

def _cache_key(query: str, mode: str) -> str:
    """生成缓存 key。"""
    content = f"{query.strip().lower()}|{mode}"
    h = hashlib.md5(content.encode()).hexdigest()[:16]
    return f"cache:{h}"


def get_query_cache(query: str, mode: str) -> Optional[Dict]:
    """获取查询缓存。"""
    try:
        r = get_redis_client()
        data = r.get(_cache_key(query, mode))
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None


def set_query_cache(query: str, mode: str, result: Dict, ttl: int = CACHE_TTL):
    """设置查询缓存。"""
    try:
        r = get_redis_client()
        r.setex(_cache_key(query, mode), ttl, json.dumps(result, ensure_ascii=False))
    except Exception:
        pass


def clear_query_cache(pattern: str = "cache:*"):
    """清空查询缓存。"""
    try:
        r = get_redis_client()
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
            print(f"[Redis] 已清空 {len(keys)} 条查询缓存")
    except Exception:
        pass


# ── Embedding 缓存 ──────────────────────────────────────────

def _emb_key(text: str) -> str:
    """生成 embedding 缓存 key。"""
    h = hashlib.md5(text.strip().encode()).hexdigest()[:16]
    return f"emb:{h}"


def get_embedding_cache(text: str) -> Optional[List[float]]:
    """获取 embedding 缓存。"""
    try:
        r = get_redis_client()
        data = r.get(_emb_key(text))
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None


def set_embedding_cache(text: str, embedding: List[float]):
    """设置 embedding 缓存（不过期）。"""
    try:
        r = get_redis_client()
        r.set(_emb_key(text), json.dumps(embedding))
    except Exception:
        pass


def get_embedding_cache_batch(texts: List[str]) -> Dict[str, List[float]]:
    """批量获取 embedding 缓存。返回 {text: embedding} 字典。"""
    result = {}
    try:
        r = get_redis_client()
        keys = [_emb_key(t) for t in texts]
        values = r.mget(keys)
        for text, val in zip(texts, values):
            if val:
                result[text] = json.loads(val)
    except Exception:
        pass
    return result


def set_embedding_cache_batch(texts: List[str], embeddings: List[List[float]]):
    """批量设置 embedding 缓存。"""
    try:
        r = get_redis_client()
        pipe = r.pipeline()
        for text, emb in zip(texts, embeddings):
            pipe.set(_emb_key(text), json.dumps(emb))
        pipe.execute()
    except Exception:
        pass


# ── 会话管理 ──────────────────────────────────────────────

def _session_key(chat_id: str) -> str:
    return f"session:{chat_id}"


def get_session(chat_id: str) -> List[Dict]:
    """获取会话消息列表。"""
    try:
        r = get_redis_client()
        data = r.get(_session_key(chat_id))
        if data:
            return json.loads(data)
    except Exception:
        pass
    return []


def save_session(chat_id: str, messages: List[Dict]):
    """保存会话消息（限制 max_history 条）。"""
    try:
        r = get_redis_client()
        # 只保留最近 max_history 条
        trimmed = messages[-MAX_HISTORY:] if len(messages) > MAX_HISTORY else messages
        r.set(_session_key(chat_id), json.dumps(trimmed, ensure_ascii=False))
        # 更新会话索引
        r.zadd("sessions:index", {chat_id: time.time()})
    except Exception:
        pass


def delete_session(chat_id: str):
    """删除会话。"""
    try:
        r = get_redis_client()
        r.delete(_session_key(chat_id))
        r.zrem("sessions:index", chat_id)
    except Exception:
        pass


def list_sessions(limit: int = 50) -> List[Dict]:
    """获取会话列表（按时间倒序）。"""
    try:
        r = get_redis_client()
        session_ids = r.zrevrange("sessions:index", 0, limit - 1)
        sessions = []
        for sid in session_ids:
            messages = get_session(sid)
            if messages:
                # 取第一条用户消息作为标题
                title = "新对话"
                for msg in messages:
                    if msg.get("role") == "user":
                        title = msg.get("text", "新对话")[:40]
                        break
                sessions.append({
                    "id": sid,
                    "title": title,
                    "message_count": len(messages),
                    "updated_at": r.zscore("sessions:index", sid),
                })
        return sessions
    except Exception:
        return []


# ── 任务队列 ──────────────────────────────────────────────

def _task_key(task_id: str) -> str:
    return f"task:{task_id}"


def create_task(task_id: str, task_type: str, params: Dict = None) -> Dict:
    """创建任务。"""
    task = {
        "id": task_id,
        "type": task_type,
        "status": "pending",
        "progress": 0,
        "result": None,
        "error": None,
        "created_at": time.time(),
        "updated_at": time.time(),
        "params": params or {},
    }
    try:
        r = get_redis_client()
        r.set(_task_key(task_id), json.dumps(task, ensure_ascii=False))
        r.rpush("task_queue:pending", task_id)
    except Exception:
        pass
    return task


def update_task(task_id: str, **kwargs):
    """更新任务状态。"""
    try:
        r = get_redis_client()
        data = r.get(_task_key(task_id))
        if data:
            task = json.loads(data)
            task.update(kwargs)
            task["updated_at"] = time.time()
            r.set(_task_key(task_id), json.dumps(task, ensure_ascii=False))
    except Exception:
        pass


def get_task(task_id: str) -> Optional[Dict]:
    """获取任务信息。"""
    try:
        r = get_redis_client()
        data = r.get(_task_key(task_id))
        if data:
            return json.loads(data)
    except Exception:
        pass
    return None


def get_next_task() -> Optional[str]:
    """从队列获取下一个待处理任务。"""
    try:
        r = get_redis_client()
        task_id = r.lpop("task_queue:pending")
        if task_id:
            r.rpush("task_queue:processing", task_id)
            update_task(task_id, status="processing")
        return task_id
    except Exception:
        return None
