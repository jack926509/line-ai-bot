"""使用者訂閱（早晨簡報開關、推送時間）"""
from db.pool import get_db


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
