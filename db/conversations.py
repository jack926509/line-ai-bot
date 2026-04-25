"""對話記憶：訊息保留 MAX_HISTORY 則"""
import json

from db.pool import get_db

MAX_HISTORY = 12


def save_message(user_id: str, role: str, content) -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO conversations (user_id, role, content) VALUES (%s, %s, %s)",
            (user_id, role, json.dumps(content, ensure_ascii=False)),
        )
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
