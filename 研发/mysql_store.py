
# MySQL 存取：用户、会话、消息、角色信息。


# 导入操作系统模块，用于读取环境变量
import os
# 导入时间模块，用于生成时间戳
import time
# 导入JSON模块，用于序列化参考来源数据
import json
# 导入类型注解，定义参数和返回值类型
from typing import Any, Dict, List, Optional

# 导入PyMySQL库，用于连接和操作MySQL数据库
import pymysql


# MySQL数据存储类：负责用户、会话、聊天记录的持久化
class MySQLStore:
    """
    Very small persistence layer for:
    - users (user_id/display_name)
    - sessions (user_id + role_code + session_id)
    - messages (question/answer with role, timestamp, sources)
    """

    # 初始化方法：配置MySQL连接参数
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        user: Optional[str] = None,
        password: Optional[str] = None,
        database: Optional[str] = None,
        charset: str = "utf8mb4",
    ):
        # 数据库主机：优先传入参数，否则读取环境变量，默认本地
        self.host = host or os.getenv("MYSQL_HOST", "127.0.0.1")
        # 数据库端口：转换为整数，优先参数，否则环境变量，默认3306
        self.port = int(port or os.getenv("MYSQL_PORT", "3306"))
        # 数据库用户名：优先参数，否则环境变量，默认root
        self.user = user or os.getenv("MYSQL_USER", "root")
        # 数据库密码：优先参数，否则环境变量，默认root
        self.password = password or os.getenv("MYSQL_PASSWORD", "root")
        # 数据库名：优先参数，否则环境变量，默认roleplay
        self.database = database or os.getenv("MYSQL_DB", "roleplay")
        # 数据库字符集，固定使用utf8mb4支持表情
        self.charset = charset

    # 内部方法：创建并返回MySQL连接
    def _connect(self):
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset=self.charset,
            # 使用字典游标，返回数据为字典格式
            cursorclass=pymysql.cursors.DictCursor,
            # 自动提交事务
            autocommit=True,
        )

    # 测试数据库是否连通
    def ping(self) -> None:
        # 创建数据库连接（with自动关闭）
        with self._connect() as conn:
            # 创建游标（with自动关闭）
            with conn.cursor() as cur:
                # 执行简单SQL测试连通性
                cur.execute("SELECT 1 AS ok")

    # 确保用户存在：不存在则插入，存在则更新昵称
    def ensure_user(self, user_id: str, display_name: Optional[str] = None) -> None:
        # 处理显示名称：截断到128字符，空值设为anonymous
        display_name = (display_name or user_id or "").strip()[:128] or "anonymous"
        # 处理用户ID：截断到64字符，空值设为anonymous
        user_id = (user_id or "").strip()[:64] or "anonymous"
        # 创建数据库连接
        with self._connect() as conn:
            with conn.cursor() as cur:
                # 插入或更新用户信息
                cur.execute(
                    """
                    INSERT INTO users (user_id, display_name)
                    VALUES (%s, %s)
                    ON DUPLICATE KEY UPDATE display_name = VALUES(display_name)
                    """,
                    (user_id, display_name),
                )

    # 确保会话存在：不存在创建，存在更新标题和最后活跃时间
    def ensure_session(
        self,
        user_id: str,
        role_code: str,
        session_id: str,
        title: Optional[str] = None,
        last_message: Optional[str] = None,
    ) -> None:
        # 格式化并截断用户ID
        user_id = (user_id or "").strip()[:64] or "anonymous"
        # 格式化并截断角色编码
        role_code = (role_code or "").strip()[:64] or "default"
        # 格式化并截断会话ID
        session_id = (session_id or "").strip()[:64] or "default"
        # 格式化并截断会话标题
        title = (title or session_id or "").strip()[:255]
        # 格式化并截断最后一条消息
        last_message = (last_message or "").strip()[:1000]
        # 创建数据库连接
        with self._connect() as conn:
            with conn.cursor() as cur:
                # 插入或更新会话信息
                cur.execute(
                    """
                    INSERT INTO chat_sessions (user_id, role_code, session_id, title, last_message, created_at, last_active_at)
                    VALUES (%s, %s, %s, %s, %s, FROM_UNIXTIME(%s), FROM_UNIXTIME(%s))
                    ON DUPLICATE KEY UPDATE
                      title = COALESCE(NULLIF(VALUES(title), ''), title),
                      last_message = COALESCE(NULLIF(VALUES(last_message), ''), last_message),
                      last_active_at = VALUES(last_active_at)
                    """,
                    (user_id, role_code, session_id, title, last_message, int(time.time()), int(time.time())),
                )

    # 更新会话最后活跃时间、标题、最后消息
    def touch_session(
        self,
        user_id: str,
        role_code: str,
        session_id: str,
        last_message: Optional[str] = None,
        title: Optional[str] = None,
    ) -> None:
        # 格式化用户ID
        user_id = (user_id or "").strip()[:64] or "anonymous"
        # 格式化角色编码
        role_code = (role_code or "").strip()[:64] or "default"
        # 格式化会话ID
        session_id = (session_id or "").strip()[:64] or "default"
        # 格式化最后消息
        last_message = (last_message or "").strip()[:1000]
        # 格式化标题
        title = (title or "").strip()[:255]
        # 创建数据库连接
        with self._connect() as conn:
            with conn.cursor() as cur:
                # 执行更新
                cur.execute(
                    """
                    UPDATE chat_sessions
                    SET
                      last_active_at = FROM_UNIXTIME(%s),
                      last_message = CASE WHEN %s <> '' THEN %s ELSE last_message END,
                      title = CASE WHEN %s <> '' THEN %s ELSE title END
                    WHERE user_id = %s AND role_code = %s AND session_id = %s
                    """,
                    (int(time.time()), last_message, last_message, title, title, user_id, role_code, session_id),
                )

    # 插入单条聊天消息
    def insert_message(
        self,
        user_id: str,
        role_code: str,
        session_id: str,
        role: str,
        content: str,
        timestamp: Optional[int] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        # 格式化用户ID
        user_id = (user_id or "").strip()[:64] or "anonymous"
        # 格式化角色编码
        role_code = (role_code or "").strip()[:64] or "default"
        # 格式化会话ID
        session_id = (session_id or "").strip()[:64] or "default"
        # 格式化消息角色（user/assistant）
        role = (role or "").strip()[:16] or "user"
        # 格式化消息内容
        content = (content or "").strip()
        # 使用传入时间戳或当前时间
        ts = int(timestamp or time.time())
        # 将参考来源序列化为JSON，截断长度
        sources_json = json.dumps(sources or [], ensure_ascii=False)[:60000]

        # 创建数据库连接并插入消息
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO chat_messages (user_id, role_code, session_id, role, content, ts, sources_json)
                    VALUES (%s, %s, %s, %s, %s, FROM_UNIXTIME(%s), %s)
                    """,
                    (user_id, role_code, session_id, role, content, ts, sources_json),
                )
        # 插入消息后，更新会话的最后活跃时间
        self.touch_session(user_id, role_code, session_id, last_message=content)

    # 更新会话标题（封装touch_session）
    def update_session_title(self, user_id: str, role_code: str, session_id: str, title: str) -> None:
        self.touch_session(user_id, role_code, session_id, title=title)

    # 列出用户某个角色下的所有会话
    def list_sessions(self, user_id: str, role_code: str) -> List[Dict[str, Any]]:
        # 格式化用户ID
        user_id = (user_id or "").strip()[:64] or "anonymous"
        # 格式化角色编码
        role_code = (role_code or "").strip()[:64] or "default"
        # 创建连接查询会话
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT session_id, title, last_message, UNIX_TIMESTAMP(last_active_at) AS updated_at
                    FROM chat_sessions
                    WHERE user_id = %s AND role_code = %s
                    ORDER BY last_active_at DESC, session_id ASC
                    """,
                    (user_id, role_code),
                )
                # 获取所有结果
                rows = cur.fetchall() or []
        # 无会话时返回默认会话
        if not rows:
            return [{
                "session_id": "default",
                "title": "新对话",
                "last_message": "",
                "updated_at": int(time.time()),
            }]
        # 标准化返回数据结构
        normalized_rows = []
        for row in rows:
            normalized_rows.append({
                "session_id": row.get("session_id") or "default",
                "title": row.get("title") or (row.get("session_id") or "新对话"),
                "last_message": row.get("last_message") or "",
                "updated_at": row.get("updated_at") or int(time.time()),
            })
        return normalized_rows

    # 获取指定会话的聊天历史记录
    def get_history(self, user_id: str, role_code: str, session_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        # 格式化用户ID
        user_id = (user_id or "").strip()[:64] or "anonymous"
        # 格式化角色编码
        role_code = (role_code or "").strip()[:64] or "default"
        # 格式化会话ID
        session_id = (session_id or "").strip()[:64] or "default"
        # 限制查询条数在1-200之间
        limit = max(1, min(int(limit), 200))
        # 创建连接查询消息
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT role, content, UNIX_TIMESTAMP(ts) AS timestamp
                    FROM chat_messages
                    WHERE user_id = %s AND role_code = %s AND session_id = %s
                    ORDER BY ts ASC, id ASC
                    LIMIT %s
                    """,
                    (user_id, role_code, session_id, limit),
                )
                rows = cur.fetchall() or []
        # 格式化返回结果
        return [{"role": r["role"], "content": r["content"], "timestamp": r["timestamp"]} for r in rows]

    # 清空会话：删除消息，重置会话信息
    def clear_session(self, user_id: str, role_code: str, session_id: str) -> None:
        # 格式化用户ID
        user_id = (user_id or "").strip()[:64] or "anonymous"
        # 格式化角色编码
        role_code = (role_code or "").strip()[:64] or "default"
        # 格式化会话ID
        session_id = (session_id or "").strip()[:64] or "default"
        # 创建连接执行清空
        with self._connect() as conn:
            with conn.cursor() as cur:
                # 删除该会话所有消息
                cur.execute(
                    "DELETE FROM chat_messages WHERE user_id=%s AND role_code=%s AND session_id=%s",
                    (user_id, role_code, session_id),
                )
                # 重置会话信息
                cur.execute(
                    """
                    UPDATE chat_sessions
                    SET last_message = '', title = '新对话', last_active_at = CURRENT_TIMESTAMP
                    WHERE user_id=%s AND role_code=%s AND session_id=%s
                    """,
                    (user_id, role_code, session_id),
                )

    # 彻底删除会话：删除消息+删除会话记录
    def delete_session(self, user_id: str, role_code: str, session_id: str) -> None:
        # 格式化用户ID
        user_id = (user_id or "").strip()[:64] or "anonymous"
        # 格式化角色编码
        role_code = (role_code or "").strip()[:64] or "default"
        # 格式化会话ID
        session_id = (session_id or "").strip()[:64] or "default"
        # 创建连接执行删除
        with self._connect() as conn:
            with conn.cursor() as cur:
                # 删除所有消息
                cur.execute(
                    "DELETE FROM chat_messages WHERE user_id=%s AND role_code=%s AND session_id=%s",
                    (user_id, role_code, session_id),
                )
                # 删除会话本身
                cur.execute(
                    "DELETE FROM chat_sessions WHERE user_id=%s AND role_code=%s AND session_id=%s",
                    (user_id, role_code, session_id),
                )