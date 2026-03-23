import os
import json
import sqlite3
from contextlib import contextmanager

# Zeabur Volume 掛載路徑，預設 /data；本機開發用 ./data
DATA_DIR = os.getenv("DATA_DIR", "./data")
DB_PATH  = os.path.join(DATA_DIR, "bot.db")


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


@contextmanager
def get_db():
    _ensure_dir()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    """建立資料表（啟動時呼叫一次）"""
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS todos (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   TEXT NOT NULL,
                content   TEXT NOT NULL,
                done      INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS conversations (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id   TEXT NOT NULL,
                role      TEXT NOT NULL,
                content   TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_todos_user ON todos(user_id);
            CREATE INDEX IF NOT EXISTS idx_conv_user  ON conversations(user_id);
        """)
    print(f"[DB] 資料庫初始化完成：{DB_PATH}")


# ─────────────────────────────────────────────
# 待辦事項
# ─────────────────────────────────────────────
def add_todo(user_id: str, content: str) -> int:
    with get_db() as conn:
        cur = conn.execute(
            "INSERT INTO todos (user_id, content) VALUES (?, ?)",
            (user_id, content),
        )
        count = conn.execute(
            "SELECT COUNT(*) FROM todos WHERE user_id = ?", (user_id,)
        ).fetchone()[0]
        return count


def get_todos(user_id: str) -> list[tuple[int, str, bool]]:
    """回傳 [(id, content, done), ...]"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, content, done FROM todos WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        return [(r[0], r[1], bool(r[2])) for r in rows]


def complete_todo(user_id: str, index: int) -> str | None:
    """以顯示序號（1-based）標記完成，回傳項目名稱或 None"""
    todos = get_todos(user_id)
    if index < 1 or index > len(todos):
        return None
    todo_id, content, _ = todos[index - 1]
    with get_db() as conn:
        conn.execute("UPDATE todos SET done = 1 WHERE id = ?", (todo_id,))
    return content


def delete_todo(user_id: str, index: int) -> str | None:
    """以顯示序號（1-based）刪除，回傳項目名稱或 None"""
    todos = get_todos(user_id)
    if index < 1 or index > len(todos):
        return None
    todo_id, content, _ = todos[index - 1]
    with get_db() as conn:
        conn.execute("DELETE FROM todos WHERE id = ?", (todo_id,))
    return content


def clear_todos(user_id: str):
    with get_db() as conn:
        conn.execute("DELETE FROM todos WHERE user_id = ?", (user_id,))


# ─────────────────────────────────────────────
# 對話記憶
# ─────────────────────────────────────────────
MAX_HISTORY = 20  # 保留最近 20 條（10 輪）


def save_message(user_id: str, role: str, content) -> None:
    """儲存一則對話（content 可能是 str 或 list，統一存 JSON）"""
    with get_db() as conn:
        conn.execute(
            "INSERT INTO conversations (user_id, role, content) VALUES (?, ?, ?)",
            (user_id, role, json.dumps(content, ensure_ascii=False)),
        )
        # 只保留最新的 MAX_HISTORY 條
        conn.execute("""
            DELETE FROM conversations
            WHERE user_id = ? AND id NOT IN (
                SELECT id FROM conversations
                WHERE user_id = ?
                ORDER BY id DESC
                LIMIT ?
            )
        """, (user_id, user_id, MAX_HISTORY))


def get_history(user_id: str) -> list[dict]:
    """取得對話歷史，格式與 Claude API 相容"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT role, content FROM conversations WHERE user_id = ? ORDER BY id",
            (user_id,),
        ).fetchall()
        return [{"role": r[0], "content": json.loads(r[1])} for r in rows]
