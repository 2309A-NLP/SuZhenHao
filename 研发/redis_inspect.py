import redis
import json


def inspect_redis():
    try:
        r = redis.Redis(host='localhost', port=6379, decode_responses=True)
        r.ping()
        print("✅ 短期记忆内容：\n")

        keys = r.keys('session:*')
        if not keys:
            print("⚠️ 未找到任何短期记忆")
            return

        for key in keys:
            print(f"📌 会话: {key}")
            messages = r.lrange(key, 0, -1)  # 时间倒序（最新在前）
            # 反转列表，使最早的在前
            messages.reverse()
            for idx, msg in enumerate(messages, 1):
                try:
                    data = json.loads(msg)
                    role = "👤用户" if data['role'] == 'user' else "🤖律师"
                    content = data['content'].strip()
                    # 截取前 40 个字符
                    short_content = content[:40] + ('...' if len(content) > 40 else '')
                    print(f"   {idx}. {role}: {short_content}")
                except:
                    print(f"   {idx}. {msg[:50]}")
            print()
    except Exception as e:
        print(f"错误: {e}")


if __name__ == "__main__":
    inspect_redis()