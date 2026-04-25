"""備忘錄 CRUD"""
from db.pool import get_db


def add_note(user_id: str, content: str) -> int:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO notes (user_id, content) VALUES (%s, %s) "
            "RETURNING (SELECT COUNT(*) FROM notes WHERE user_id = %s)",
            (user_id, content, user_id),
        )
        return cur.fetchone()[0]


def get_notes(user_id: str) -> list[tuple]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, content, created_at FROM notes "
            "WHERE user_id = %s ORDER BY id DESC LIMIT 20",
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
