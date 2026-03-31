import os
import json
import psycopg2
from contextlib import contextmanager
from datetime import date, timedelta

DATABASE_URL = os.getenv("DATABASE_URL", "")


@contextmanager
def get_db():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _column_exists(cur, table: str, column: str) -> bool:
    """檢查資料表中是否已存在指定欄位"""
    cur.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return cur.fetchone() is not None


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
        # 新增 category 與 due_date 欄位（相容既有部署）
        if not _column_exists(cur, "todos", "category"):
            cur.execute("ALTER TABLE todos ADD COLUMN category TEXT DEFAULT '一般'")
        if not _column_exists(cur, "todos", "due_date"):
            cur.execute("ALTER TABLE todos ADD COLUMN due_date DATE")

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
            CREATE TABLE IF NOT EXISTS notes (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                content    TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS gcal_tokens (
                user_id     TEXT PRIMARY KEY,
                credentials TEXT NOT NULL
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_todos_user ON todos(user_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id)
        """)
    print("[DB] PostgreSQL 資料庫初始化完成")


# ─────────────────────────────────────────────
# 待辦事項
# ─────────────────────────────────────────────
def add_todo(user_id: str, content: str, category: str = "一般", due_date: date | None = None) -> int:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO todos (user_id, content, category, due_date) VALUES (%s, %s, %s, %s)",
            (user_id, content, category, due_date),
        )
        cur.execute(
            "SELECT COUNT(*) FROM todos WHERE user_id = %s", (user_id,)
        )
        return cur.fetchone()[0]


def get_todos(user_id: str) -> list[tuple[int, str, bool, str, date | None]]:
    """回傳 [(id, content, done, category, due_date), ...]"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, content, done, category, due_date FROM todos WHERE user_id = %s ORDER BY id",
            (user_id,),
        )
        return [(r[0], r[1], bool(r[2]), r[3], r[4]) for r in cur.fetchall()]


def get_due_todos() -> list[tuple[str, str, date]]:
    """回傳所有用戶中今天或明天到期且未完成的待辦 [(user_id, content, due_date), ...]"""
    today = date.today()
    tomorrow = today + timedelta(days=1)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, content, due_date FROM todos WHERE done = FALSE AND due_date IN (%s, %s) ORDER BY due_date, id",
            (today, tomorrow),
        )
        return [(r[0], r[1], r[2]) for r in cur.fetchall()]


def complete_todo(user_id: str, index: int) -> str | None:
    """以顯示序號（1-based）標記完成，回傳項目名稱或 None"""
    todos = get_todos(user_id)
    if index < 1 or index > len(todos):
        return None
    todo_id, content, _, _, _ = todos[index - 1]
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE todos SET done = TRUE WHERE id = %s", (todo_id,))
    return content


def delete_todo(user_id: str, index: int) -> str | None:
    """以顯示序號（1-based）刪除，回傳項目名稱或 None"""
    todos = get_todos(user_id)
    if index < 1 or index > len(todos):
        return None
    todo_id, content, _, _, _ = todos[index - 1]
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM todos WHERE id = %s", (todo_id,))
    return content


def clear_todos(user_id: str):
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM todos WHERE user_id = %s", (user_id,))


# ─────────────────────────────────────────────
# 筆記
# ─────────────────────────────────────────────
def add_note(user_id: str, content: str) -> int:
    """新增筆記，回傳該用戶的筆記總數"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO notes (user_id, content) VALUES (%s, %s)",
            (user_id, content),
        )
        cur.execute(
            "SELECT COUNT(*) FROM notes WHERE user_id = %s", (user_id,)
        )
        return cur.fetchone()[0]


def get_notes(user_id: str) -> list[tuple[int, str, str]]:
    """回傳 [(id, content, created_at), ...] 最新在前，最多 20 筆"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, content, created_at FROM notes WHERE user_id = %s ORDER BY id DESC LIMIT 20",
            (user_id,),
        )
        return [(r[0], r[1], r[2]) for r in cur.fetchall()]


def delete_note(user_id: str, index: int) -> str | None:
    """以顯示序號（1-based，最新在前）刪除筆記，回傳內容或 None"""
    notes = get_notes(user_id)
    if index < 1 or index > len(notes):
        return None
    note_id, content, _ = notes[index - 1]
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM notes WHERE id = %s", (note_id,))
    return content


def clear_notes(user_id: str):
    """清除指定用戶的所有筆記"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM notes WHERE user_id = %s", (user_id,))


# ─────────────────────────────────────────────
# Google Calendar 憑證
# ─────────────────────────────────────────────
def save_gcal_token(user_id: str, creds_json: str) -> None:
    """新增或更新 Google Calendar 憑證（JSON 字串）"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO gcal_tokens (user_id, credentials) VALUES (%s, %s)
            ON CONFLICT (user_id) DO UPDATE SET credentials = EXCLUDED.credentials
        """, (user_id, creds_json))


def get_gcal_token(user_id: str) -> str | None:
    """取得 Google Calendar 憑證 JSON 字串，不存在回傳 None"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT credentials FROM gcal_tokens WHERE user_id = %s", (user_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None


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


def clear_history(user_id: str):
    """清除指定用戶的對話記憶"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))


def get_history(user_id: str) -> list[dict]:
    """取得對話歷史，格式與 Claude API 相容"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT role, content FROM conversations WHERE user_id = %s ORDER BY id",
            (user_id,),
        )
        return [{"role": r[0], "content": json.loads(r[1])} for r in cur.fetchall()]
