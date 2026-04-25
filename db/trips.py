"""旅遊行程：含 places 與 gcal_ids（JSONB）"""
import json

from db.pool import get_db


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
