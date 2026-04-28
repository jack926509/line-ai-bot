"""Claude API token 使用量持久化。

每次呼叫累計到當日彙總（user_id × usage_date × model）以節省寫入次數。
查詢介面提供 today / month 兩種粒度。
"""
from db.pool import get_db, logger


def record_usage(
    user_id: str,
    model: str,
    input_tokens: int,
    cache_write_tokens: int,
    cache_read_tokens: int,
    output_tokens: int,
    cost_usd: float,
) -> None:
    """累計一次 Claude 呼叫的使用量到當日彙總。

    user_id 為空字串時表示無關聯使用者（如排程任務的內部呼叫），
    一律記到 user_id='__system__'，便於日後彙總成本。
    """
    uid = user_id or "__system__"
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO token_usage (
                    user_id, usage_date, model,
                    input_tokens, cache_write_tokens, cache_read_tokens,
                    output_tokens, cost_usd, calls
                ) VALUES (%s, CURRENT_DATE, %s, %s, %s, %s, %s, %s, 1)
                ON CONFLICT (user_id, usage_date, model) DO UPDATE SET
                    input_tokens       = token_usage.input_tokens       + EXCLUDED.input_tokens,
                    cache_write_tokens = token_usage.cache_write_tokens + EXCLUDED.cache_write_tokens,
                    cache_read_tokens  = token_usage.cache_read_tokens  + EXCLUDED.cache_read_tokens,
                    output_tokens      = token_usage.output_tokens      + EXCLUDED.output_tokens,
                    cost_usd           = token_usage.cost_usd           + EXCLUDED.cost_usd,
                    calls              = token_usage.calls              + 1
                """,
                (uid, model, input_tokens, cache_write_tokens, cache_read_tokens,
                 output_tokens, cost_usd),
            )
    except Exception as e:
        # 記錄失敗不應影響主流程
        logger.warning(f"token_usage 寫入失敗: {e}")


def get_usage_summary(user_id: str) -> dict:
    """回傳該使用者今日 / 本月的呼叫數與成本。"""
    uid = user_id or "__system__"
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN usage_date = CURRENT_DATE THEN calls    END), 0) AS today_calls,
                COALESCE(SUM(CASE WHEN usage_date = CURRENT_DATE THEN cost_usd END), 0) AS today_cost,
                COALESCE(SUM(CASE WHEN date_trunc('month', usage_date) = date_trunc('month', CURRENT_DATE)
                                  THEN calls    END), 0) AS month_calls,
                COALESCE(SUM(CASE WHEN date_trunc('month', usage_date) = date_trunc('month', CURRENT_DATE)
                                  THEN cost_usd END), 0) AS month_cost
            FROM token_usage WHERE user_id = %s
            """,
            (uid,),
        )
        row = cur.fetchone()
    return {
        "today_calls": int(row[0] or 0),
        "today_cost": float(row[1] or 0.0),
        "month_calls": int(row[2] or 0),
        "month_cost": float(row[3] or 0.0),
    }


def cleanup_token_usage(retention_days: int = 365) -> int:
    """清理超過 retention_days 天的明細（個人用預設保留一年）。"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM token_usage WHERE usage_date < CURRENT_DATE - %s::int",
            (retention_days,),
        )
        deleted = cur.rowcount or 0
        if deleted:
            logger.info(f"token_usage 清理：刪除 {deleted} 筆 (retention={retention_days}d)")
        return deleted
