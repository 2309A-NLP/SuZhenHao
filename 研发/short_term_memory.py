# 短期记忆 ShortTermMemory：
# 基于 Redis 保存最近 N 轮对话，按会话隔离。


# 导入json模块，用于序列化和反序列化消息数据
import json
# 导入os模块，用于读取环境变量
import os
# 导入time模块，用于生成时间戳
import time
# 导入redis模块，用于连接Redis缓存
import redis

# 短期记忆类：基于Redis/内存存储对话历史，用于上下文理解
class ShortTermMemory:
    # 初始化方法：配置Redis连接、最大历史数、过期时间
    def __init__(self, redis_host="localhost", redis_port=6379, max_history=20):
        # 从环境变量读取Redis连接超时时间，默认2秒
        connect_timeout = float(os.getenv("REDIS_CONNECT_TIMEOUT", "2"))
        # 创建Redis客户端实例
        self.redis = redis.Redis(
            host=redis_host,                # Redis主机地址
            port=redis_port,                # Redis端口
            decode_responses=True,          # 自动解码为字符串
            socket_connect_timeout=connect_timeout,  # 连接超时
            socket_timeout=connect_timeout,          # 操作超时
        )
        # 最大保留的对话历史条数
        self.max_history = max_history
        # 缓存过期时间：1800秒 = 30分钟
        self.ttl = 1800
        # Redis不可用时的本地内存存储（字典）
        self._fallback_store = {}
        # Redis不可用时的本地会话列表存储
        self._fallback_sessions = {}
        try:
            # 测试Redis是否可用
            self.redis.ping()
            # Redis可用标记设为True
            self._redis_available = True
        except Exception:
            # Redis连接失败，标记为不可用
            self._redis_available = False
            # 打印降级提示
            print("[ShortTermMemory] Redis 不可用，启用进程内短期记忆（重启进程后会丢失）。")

    # 生成单条会话的Redis Key
    def _session_key(self, user_id: str, role_code: str, session_id: str) -> str:
        return f"session:{user_id}:{role_code}:{session_id}"

    # 生成用户+角色的会话集合Redis Key
    def _session_set_key(self, user_id: str, role_code: str) -> str:
        return f"sessions:{user_id}:{role_code}"

    # 添加一条消息到短期记忆
    def add_message(self, user_id: str, role_code: str, session_id: str, role: str, content: str):
        # 构造消息结构体（角色、内容、时间戳）
        msg = {"role": role, "content": content, "timestamp": int(time.time())}
        # 如果Redis可用，使用Redis存储
        if self._redis_available:
            # 获取会话Key
            key = self._session_key(user_id, role_code, session_id)
            # 获取会话集合Key
            session_set_key = self._session_set_key(user_id, role_code)
            # 左推入消息（最新消息在前）
            self.redis.lpush(key, json.dumps(msg))
            # 裁剪列表，只保留最新max_history条
            self.redis.ltrim(key, 0, self.max_history - 1)
            # 设置Key过期时间
            self.redis.expire(key, self.ttl)
            # 将会话ID加入集合
            self.redis.sadd(session_set_key, session_id)
            # 刷新集合过期时间
            self.redis.expire(session_set_key, self.ttl)
            # 结束Redis分支
            return

        # Redis不可用，使用本地内存存储
        key = (user_id, role_code, session_id)
        # 确保key对应的列表存在
        self._fallback_store.setdefault(key, [])
        # 追加消息
        self._fallback_store[key].append(msg)
        # 裁剪消息列表，保留最新max_history条
        self._fallback_store[key] = self._fallback_store[key][-self.max_history :]
        # 将会话ID加入会话集合
        self._fallback_sessions.setdefault((user_id, role_code), set()).add(session_id)

    # 获取指定会话的完整对话历史
    def get_history(self, user_id: str, role_code: str, session_id: str) -> list:
        # Redis可用时从Redis读取
        if self._redis_available:
            key = self._session_key(user_id, role_code, session_id)
            # 获取列表所有元素
            items = self.redis.lrange(key, 0, -1)
            # 逆序并反序列化为对象返回
            return [json.loads(item) for item in reversed(items)]
        # Redis不可用时从本地内存读取
        return list(self._fallback_store.get((user_id, role_code, session_id), []))

    # 清空指定会话
    def clear_session(self, user_id: str, role_code: str, session_id: str):
        # Redis可用时删除Redis数据
        if self._redis_available:
            session_set_key = self._session_set_key(user_id, role_code)
            # 删除会话消息
            self.redis.delete(self._session_key(user_id, role_code, session_id))
            # 从会话集合中移除
            self.redis.srem(session_set_key, session_id)
            return
        # Redis不可用时删除本地内存数据
        self._fallback_store.pop((user_id, role_code, session_id), None)
        # 从会话集合中移除
        if (user_id, role_code) in self._fallback_sessions:
            self._fallback_sessions[(user_id, role_code)].discard(session_id)

    # 列出用户+角色下的所有会话ID
    def list_sessions(self, user_id: str, role_code: str) -> list:
        # Redis可用时从集合获取
        if self._redis_available:
            session_set_key = self._session_set_key(user_id, role_code)
            session_ids = list(self.redis.smembers(session_set_key))
        else:
            # 本地内存获取
            session_ids = list(self._fallback_sessions.get((user_id, role_code), set()))
        # 无会话时返回默认default
        if not session_ids:
            return ["default"]
        # 排序后返回
        session_ids.sort()
        return session_ids

    # 确保会话存在（创建会话，不添加消息）
    def ensure_session(self, user_id: str, role_code: str, session_id: str) -> None:
        # Redis可用
        if self._redis_available:
            session_set_key = self._session_set_key(user_id, role_code)
            # 添加会话ID到集合
            self.redis.sadd(session_set_key, session_id)
            # 刷新过期时间
            self.redis.expire(session_set_key, self.ttl)
            return
        # 本地内存模式：添加会话ID
        self._fallback_sessions.setdefault((user_id, role_code), set()).add(session_id)