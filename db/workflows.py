"""多步驟工作流（目前主用於提醒：一次性 / 每日 / 每週）。

steps JSONB 結構：
  {"kind": "once"|"daily"|"weekly", "text": "...", "spec": "HH:MM" or "N|HH:MM"}
state: pending（待執行）/ done（一次性已執行）/ cancelled
next_run_at: 下一次應觸發時間（UTC）
"""
import json
from db.pool import get_db, logger


def add_workflow(user_id: str, name: str, steps: dict, next_run_at) -> int:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO workflows (user_id, name, steps, state, next_run_at)
            VALUES (%s, %s, %s::jsonb, 'pending', %s)
            RETURNING id
            """,
            (user_id, name, json.dumps(steps, ensure_ascii=False), next_run_at),
        )
        return cur.fetchone()[0]


def list_workflows(user_id: str, include_done: bool = False) -> list[tuple]:
    sql = (
        "SELECT id, name, steps, state, next_run_at FROM workflows "
        "WHERE user_id=%s"
    )
    if not include_done:
        sql += " AND state='pending'"
    sql += " ORDER BY next_run_at NULLS LAST, id"
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(sql, (user_id,))
        return cur.fetchall()


def cancel_workflow(user_id: str, wf_id: int) -> str | None:
    """設為 cancelled。回傳被取消的 name；找不到回 None。"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "UPDATE workflows SET state='cancelled' "
            "WHERE id=%s AND user_id=%s AND state='pending' RETURNING name",
            (wf_id, user_id),
        )
        row = cur.fetchone()
        return row[0] if row else None


def fetch_due(now) -> list[tuple]:
    """取得所有到期且尚未執行的工作流（跨使用者，由排程器呼叫）。"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, user_id, name, steps, next_run_at FROM workflows "
            "WHERE state='pending' AND next_run_at IS NOT NULL AND next_run_at <= %s "
            "ORDER BY next_run_at",
            (now,),
        )
        return cur.fetchall()


def mark_done(wf_id: int) -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE workflows SET state='done' WHERE id=%s", (wf_id,))


def update_next_run(wf_id: int, next_run_at) -> None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("UPDATE workflows SET next_run_at=%s WHERE id=%s", (next_run_at, wf_id))


def cleanup_workflows(retention_days: int = 30) -> int:
    """清掉 30 天前的 done / cancelled 紀錄。"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM workflows "
            "WHERE state IN ('done','cancelled') "
            "AND next_run_at < NOW() - (%s || ' days')::interval",
            (retention_days,),
        )
        deleted = cur.rowcount or 0
        if deleted:
            logger.info(f"workflows 清理：刪除 {deleted} 筆 (retention={retention_days}d)")
        return deleted
