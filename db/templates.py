"""公文範本庫"""
from db.pool import get_db


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
