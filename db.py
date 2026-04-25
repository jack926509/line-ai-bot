"""PostgreSQL 資料庫模組（連線池 + 對話記憶 + 待辦 + 記事）"""
import os
import json
import logging
from contextlib import contextmanager
from datetime import date, timedelta

import psycopg2
from psycopg2 import pool

logger = logging.getLogger("lumio.db")

DATABASE_URL = os.getenv("DATABASE_URL", "")

_pool: pool.SimpleConnectionPool | None = None


def _get_pool() -> pool.SimpleConnectionPool:
    global _pool
    if _pool is None:
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

        # ─── Stage 0：推播 / 訂閱 / 範本 / 旅遊 / 工作流 ───
        cur.execute("""
            CREATE TABLE IF NOT EXISTS subscriptions (
                user_id    TEXT PRIMARY KEY,
                briefing   BOOLEAN DEFAULT TRUE,
                brief_time TIME    DEFAULT '08:00',
                tz         TEXT    DEFAULT 'Asia/Taipei',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS push_log (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                kind       TEXT NOT NULL,
                ref_date   DATE NOT NULL,
                pushed_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (user_id, kind, ref_date)
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS doc_templates (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                name       TEXT NOT NULL,
                category   TEXT DEFAULT '一般',
                body       TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_tpl_user ON doc_templates(user_id)")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS trips (
                id         SERIAL PRIMARY KEY,
                user_id    TEXT NOT NULL,
                name       TEXT NOT NULL,
                start_date DATE NOT NULL,
                end_date   DATE NOT NULL,
                places     JSONB DEFAULT '[]'::jsonb,
                gcal_ids   JSONB DEFAULT '[]'::jsonb,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_trips_user ON trips(user_id)")
        # 多步驟工作流預留（暫不啟用，避免日後遷移痛苦）
        cur.execute("""
            CREATE TABLE IF NOT EXISTS workflows (
                id           SERIAL PRIMARY KEY,
                user_id      TEXT NOT NULL,
                name         TEXT NOT NULL,
                steps        JSONB DEFAULT '[]'::jsonb,
                state        TEXT DEFAULT 'pending',
                next_run_at  TIMESTAMP,
                created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    logger.info("PostgreSQL 初始化完成（含 Stage 0 推播相關表）")


# ─── 訂閱與推播 ───

def upsert_subscription(user_id: str) -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO subscriptions (user_id) VALUES (%s) ON CONFLICT (user_id) DO NOTHING",
            (user_id,),
        )


def get_subscription(user_id: str) -> dict | None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT user_id, briefing, brief_time, tz FROM subscriptions WHERE user_id=%s",
            (user_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {"user_id": row[0], "briefing": row[1], "brief_time": str(row[2])[:5], "tz": row[3]}


def set_briefing(user_id: str, enabled: bool) -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE subscriptions SET briefing=%s WHERE user_id=%s", (enabled, user_id))


def get_briefing_subscribers() -> list[str]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM subscriptions WHERE briefing=TRUE")
        return [r[0] for r in cur.fetchall()]


def has_pushed_today(user_id: str, kind: str) -> bool:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM push_log WHERE user_id=%s AND kind=%s AND ref_date=CURRENT_DATE",
            (user_id, kind),
        )
        return cur.fetchone() is not None


def mark_pushed(user_id: str, kind: str) -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO push_log (user_id, kind, ref_date) VALUES (%s, %s, CURRENT_DATE) "
            "ON CONFLICT DO NOTHING",
            (user_id, kind),
        )


# ─── 公文範本庫 ───

def add_template(user_id: str, name: str, category: str, body: str) -> int:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO doc_templates (user_id, name, category, body) "
            "VALUES (%s, %s, %s, %s) RETURNING id",
            (user_id, name, category, body),
        )
        return cur.fetchone()[0]


def list_templates(user_id: str) -> list[tuple]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, category, body FROM doc_templates "
            "WHERE user_id=%s ORDER BY category, id",
            (user_id,),
        )
        return cur.fetchall()


def delete_template(template_id: int) -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM doc_templates WHERE id=%s", (template_id,))


# ─── 旅遊行程 ───

def add_trip(user_id: str, name: str, start_date: str, end_date: str,
             places: list[dict], gcal_ids: list[str] | None = None) -> int:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO trips (user_id, name, start_date, end_date, places, gcal_ids) "
            "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (user_id, name, start_date, end_date,
             json.dumps(places, ensure_ascii=False),
             json.dumps(gcal_ids or [], ensure_ascii=False)),
        )
        return cur.fetchone()[0]


def list_trips(user_id: str) -> list[tuple]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, start_date, end_date, places, gcal_ids FROM trips "
            "WHERE user_id=%s ORDER BY start_date DESC",
            (user_id,),
        )
        return cur.fetchall()


def delete_trip(trip_id: int) -> tuple | None:
    """回傳 (name, gcal_ids) 供呼叫者清理 GCal"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT name, gcal_ids FROM trips WHERE id=%s", (trip_id,))
        row = cur.fetchone()
        if not row:
            return None
        cur.execute("DELETE FROM trips WHERE id=%s", (trip_id,))
        return row


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
