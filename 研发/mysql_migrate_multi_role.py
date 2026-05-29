import pymysql
from role_config import ROLE_CONFIGS, get_role_prompt


def main():
    conn = pymysql.connect(
        host="127.0.0.1",
        user="root",
        password="root",
        database="roleplay",
        charset="utf8mb4",
        autocommit=True,
    )
    cur = conn.cursor()

    cur.execute("SHOW COLUMNS FROM chat_sessions")
    chat_session_columns = {row[0] for row in cur.fetchall()}
    statements = []

    if "role_code" not in chat_session_columns:
        statements.append(
            "ALTER TABLE chat_sessions ADD COLUMN role_code VARCHAR(64) NOT NULL DEFAULT 'psychologist' AFTER user_id"
        )
    if "title" not in chat_session_columns:
        statements.append(
            "ALTER TABLE chat_sessions ADD COLUMN title VARCHAR(255) DEFAULT '新对话' AFTER session_id"
        )
    if "last_message" not in chat_session_columns:
        statements.append("ALTER TABLE chat_sessions ADD COLUMN last_message TEXT AFTER title")

    cur.execute("SHOW INDEX FROM chat_sessions")
    chat_session_indexes = {row[2] for row in cur.fetchall()}
    if "uniq_user_session" in chat_session_indexes:
        statements.append("ALTER TABLE chat_sessions DROP INDEX uniq_user_session")
    if "uniq_user_role_session" not in chat_session_indexes:
        statements.append(
            "ALTER TABLE chat_sessions ADD UNIQUE KEY uniq_user_role_session (user_id, role_code, session_id)"
        )
    if "idx_user_role_last_active" not in chat_session_indexes:
        statements.append(
            "ALTER TABLE chat_sessions ADD INDEX idx_user_role_last_active (user_id, role_code, last_active_at)"
        )

    cur.execute("SHOW COLUMNS FROM chat_messages")
    chat_message_columns = {row[0] for row in cur.fetchall()}
    if "role_code" not in chat_message_columns:
        statements.append(
            "ALTER TABLE chat_messages ADD COLUMN role_code VARCHAR(64) NOT NULL DEFAULT 'psychologist' AFTER user_id"
        )

    cur.execute("SHOW INDEX FROM chat_messages")
    chat_message_indexes = {row[2] for row in cur.fetchall()}
    if "idx_user_role_session_ts" not in chat_message_indexes:
        statements.append(
            "ALTER TABLE chat_messages ADD INDEX idx_user_role_session_ts (user_id, role_code, session_id, ts)"
        )

    for statement in statements:
        print(statement)
        cur.execute(statement)

    for role in ROLE_CONFIGS:
        cur.execute(
            """
            INSERT INTO roles (role_code, role_name, prompt_template, is_active)
            VALUES (%s, %s, %s, 1)
            ON DUPLICATE KEY UPDATE
              role_name = VALUES(role_name),
              prompt_template = VALUES(prompt_template),
              is_active = VALUES(is_active)
            """,
            (role["role_code"], role["display_name"], get_role_prompt(role["role_code"])),
        )

    print("migration ok")
    conn.close()


if __name__ == "__main__":
    main()
