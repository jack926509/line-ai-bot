"""LINE 訊息去重：避免 webhook 重送造成重複處理。"""
from db.pool import get_db, logger


def is_processed(message_id: str) -> bool:
    """檢查訊息是否已處理。回傳 True 代表是重送，應略過。"""
    if not message_id:
        return False
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT 1 FROM processed_messages WHERE message_id=%s",
            (message_id,),
        )
        return cur.fetchone() is not None


def mark_processed(message_id: str) -> bool:
    """標記訊息已處理。回傳 True 代表本次成功插入（首次處理）；
    False 代表已存在（並發時的另一個 worker 已先寫入）。"""
    if not message_id:
        return True
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO processed_messages (message_id) VALUES (%s) "
            "ON CONFLICT DO NOTHING",
            (message_id,),
        )
        return (cur.rowcount or 0) > 0


def cleanup_processed_messages(retention_days: int = 7) -> int:
    """清理超過 retention_days 天前的訊息紀錄。LINE 重送窗口遠短於 7 天。"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM processed_messages "
            "WHERE created_at < NOW() - (%s || ' days')::interval",
            (retention_days,),
        )
        deleted = cur.rowcount or 0
        if deleted:
            logger.info(f"processed_messages 清理：刪除 {deleted} 筆 (retention={retention_days}d)")
        return deleted
