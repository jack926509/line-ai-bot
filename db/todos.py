"""待辦事項 CRUD"""
from datetime import date

from db.pool import get_db


def add_todo(user_id: str, content: str, category: str = "一般", due_date: date | None = None) -> int:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO todos (user_id, content, category, due_date) VALUES (%s, %s, %s, %s) "
            "RETURNING (SELECT COUNT(*) FROM todos WHERE user_id = %s)",
            (user_id, content, category, due_date, user_id),
        )
        return cur.fetchone()[0]


def get_todos(user_id: str) -> list[tuple]:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, content, done, category, due_date FROM todos "
            "WHERE user_id = %s ORDER BY category, id",
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
