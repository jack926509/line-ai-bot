import os
import json
import psycopg2
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL", "")


@contextmanager
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """建立資料表（啟動時呼叫一次）"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                content    TEXT NOT NULL,
                done       BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                role       TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_todos_user ON todos(user_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id)
        """)
    print("[DB] PostgreSQL 資料庫初始化完成")


# ─────────────────────────────────────────────
# 待辦事項
# ─────────────────────────────────────────────
def add_todo(user_id: str, content: str) -> int:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO todos (user_id, content) VALUES (%s, %s)",
            (user_id, content),
        )
        cur.execute(
            "SELECT COUNT(*) FROM todos WHERE user_id = %s", (user_id,)
        )
        return cur.fetchone()[0]


def get_todos(user_id: str) -> list[tuple[int, str, bool]]:
    """回傳 [(id, content, done), ...]"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, content, done FROM todos WHERE user_id = %s ORDER BY id",
            (user_id,),
        )
        return [(r[0], r[1], bool(r[2])) for r in cur.fetchall()]


def complete_todo(user_id: str, index: int) -> str | None:
    """以顯示序號（1-based）標記完成，回傳項目名稱或 None"""
    todos = get_todos(user_id)
    if index < 1 or index > len(todos):
        return None
    todo_id, content, _ = todos[index - 1]
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE todos SET done = TRUE WHERE id = %s", (todo_id,))
    return content


def delete_todo(user_id: str, index: int) -> str | None:
    """以顯示序號（1-based）刪除，回傳項目名稱或 None"""
    todos = get_todos(user_id)
    if index < 1 or index > len(todos):
        return None
    todo_id, content, _ = todos[index - 1]
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM todos WHERE id = %s", (todo_id,))
    return content


def clear_todos(user_id: str):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM todos WHERE user_id = %s", (user_id,))


# ─────────────────────────────────────────────
# 對話記憶
# ─────────────────────────────────────────────
MAX_HISTORY = 20  # 保留最近 20 條（10 輪）


def save_message(user_id: str, role: str, content) -> None:
    """儲存一則對話（content 可能是 str 或 list，統一存 JSON）"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO conversations (user_id, role, content) VALUES (%s, %s, %s)",
            (user_id, role, json.dumps(content, ensure_ascii=False)),
        )
        # 只保留最新的 MAX_HISTORY 條
        cur.execute("""
            DELETE FROM conversations
            WHERE user_id = %s AND id NOT IN (
                SELECT id FROM conversations
                WHERE user_id = %s
                ORDER BY id DESC
                LIMIT %s
            )
        """, (user_id, user_id, MAX_HISTORY))


def get_history(user_id: str) -> list[dict]:
    """取得對話歷史，格式與 Claude API 相容"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT role, content FROM conversations WHERE user_id = %s ORDER BY id",
            (user_id,),
        )
        return [{"role": r[0], "content": json.loads(r[1])} for r in cur.fetchall()]
