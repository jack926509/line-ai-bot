"""PostgreSQL 資料庫模組（連線池 + 對話記憶 + 待辦 + 記事）"""
import os
import json
from contextlib import contextmanager
from datetime import date, timedelta

import psycopg2
from psycopg2 import pool

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool: pool.SimpleConnectionPool | None = None


def _get_pool() -> pool.SimpleConnectionPool:
    global _pool
    if _pool is None or _pool.closed:
        _pool = pool.SimpleConnectionPool(1, 5, DATABASE_URL)
    return _pool


@contextmanager
def get_db():
    p = _get_pool()
    conn = p.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        p.putconn(conn)


def _column_exists(cur, table: str, column: str) -> bool:
    cur.execute("""
        SELECT 1 FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
    """, (table, column))
    return cur.fetchone() is not None


def init_db():
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS todos (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                content    TEXT NOT NULL,
                done       BOOLEAN DEFAULT FALSE,
                category   TEXT DEFAULT '一般',
                due_date   DATE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
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
        cur.execute("CREATE INDEX IF NOT EXISTS idx_todos_user ON todos(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_conv_user_id ON conversations(user_id, id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_notes_user ON notes(user_id)")
    print("[DB] PostgreSQL 初始化完成（連線池 1~5）")


# ─── 待辦事項 ───

def add_todo(user_id: str, content: str, category: str = "一般", due_date: date | None = None) -> int:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO todos (user_id, content, category, due_date) VALUES (%s, %s, %s, %s) RETURNING (SELECT COUNT(*) FROM todos WHERE user_id = %s)",
            (user_id, content, category, due_date, user_id),
        )
        return cur.fetchone()[0]


def get_todos(user_id: str) -> list[tuple]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, content, done, category, due_date FROM todos WHERE user_id = %s ORDER BY category, id",
            (user_id,),
        )
        return cur.fetchall()


def complete_todo(user_id: str, index: int) -> str | None:
    todos = get_todos(user_id)
    if index < 1 or index > len(todos):
        return None
    todo_id, content = todos[index - 1][0], todos[index - 1][1]
    with get_db() as conn:
        conn.cursor().execute("UPDATE todos SET done = TRUE WHERE id = %s", (todo_id,))
    return content


def delete_todo(user_id: str, index: int) -> str | None:
    todos = get_todos(user_id)
    if index < 1 or index > len(todos):
        return None
    todo_id, content = todos[index - 1][0], todos[index - 1][1]
    with get_db() as conn:
        conn.cursor().execute("DELETE FROM todos WHERE id = %s", (todo_id,))
    return content


def clear_todos(user_id: str):
    with get_db() as conn:
        conn.cursor().execute("DELETE FROM todos WHERE user_id = %s", (user_id,))


# ─── 記事 ───

def add_note(user_id: str, content: str) -> int:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO notes (user_id, content) VALUES (%s, %s) RETURNING (SELECT COUNT(*) FROM notes WHERE user_id = %s)",
            (user_id, content, user_id),
        )
        return cur.fetchone()[0]


def get_notes(user_id: str) -> list[tuple]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, content, created_at FROM notes WHERE user_id = %s ORDER BY id DESC LIMIT 20",
            (user_id,),
        )
        return cur.fetchall()


def delete_note(user_id: str, index: int) -> str | None:
    notes = get_notes(user_id)
    if index < 1 or index > len(notes):
        return None
    note_id, content = notes[index - 1][0], notes[index - 1][1]
    with get_db() as conn:
        conn.cursor().execute("DELETE FROM notes WHERE id = %s", (note_id,))
    return content


def clear_notes(user_id: str):
    with get_db() as conn:
        conn.cursor().execute("DELETE FROM notes WHERE user_id = %s", (user_id,))


# ─── 對話記憶 ───

MAX_HISTORY = 12


def save_message(user_id: str, role: str, content) -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO conversations (user_id, role, content) VALUES (%s, %s, %s)",
            (user_id, role, json.dumps(content, ensure_ascii=False)),
        )
        # 用 CTE 高效裁剪，利用 (user_id, id) 複合索引
        cur.execute("""
            DELETE FROM conversations
            WHERE user_id = %s
              AND id < (
                  SELECT id FROM conversations
                  WHERE user_id = %s
                  ORDER BY id DESC
                  OFFSET %s
                  LIMIT 1
              )
        """, (user_id, user_id, MAX_HISTORY))


def clear_history(user_id: str):
    with get_db() as conn:
        conn.cursor().execute("DELETE FROM conversations WHERE user_id = %s", (user_id,))


def get_history(user_id: str) -> list[dict]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT role, content FROM conversations WHERE user_id = %s ORDER BY id",
            (user_id,),
        )
        return [{"role": r[0], "content": json.loads(r[1])} for r in cur.fetchall()]
