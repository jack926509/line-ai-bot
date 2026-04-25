"""推播去重：每日同 kind 只推一次"""
from db.pool import get_db


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
