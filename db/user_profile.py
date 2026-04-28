"""使用者長期記憶（暱稱、偏好、常用聯絡人等）。

資料模型：扁平 key-value，按 user_id 分群。
- 寫入：UPSERT；同 key 覆寫 value
- 容量：每使用者上限 50 條（超過時拒絕，由 Claude 提示使用者整理）
"""
from db.pool import get_db, logger

_MAX_FACTS_PER_USER = 50


def remember(user_id: str, key: str, value: str) -> tuple[bool, str]:
    """寫入或更新一條記憶。回傳 (是否成功, 訊息)。"""
    if not key.strip() or not value.strip():
        return False, "key 與 value 皆不可為空"
    key, value = key.strip()[:50], value.strip()[:500]
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM user_profile WHERE user_id=%s", (user_id,))
        count = cur.fetchone()[0]
        cur.execute("SELECT 1 FROM user_profile WHERE user_id=%s AND fact_key=%s", (user_id, key))
        is_update = cur.fetchone() is not None
        if not is_update and count >= _MAX_FACTS_PER_USER:
            return False, f"記憶已達上限 {_MAX_FACTS_PER_USER} 條，請先整理"
        cur.execute(
            """
            INSERT INTO user_profile (user_id, fact_key, fact_value)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id, fact_key) DO UPDATE SET
                fact_value = EXCLUDED.fact_value,
                updated_at = NOW()
            """,
            (user_id, key, value),
        )
    logger.info(f"profile {'updated' if is_update else 'created'} user={user_id} key={key}")
    return True, "已更新" if is_update else "已記住"


def forget(user_id: str, key: str) -> bool:
    """刪除一條記憶。回傳是否有刪到。"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM user_profile WHERE user_id=%s AND fact_key=%s",
            (user_id, key.strip()),
        )
        return (cur.rowcount or 0) > 0


def list_facts(user_id: str) -> list[tuple[str, str]]:
    """回傳該使用者所有記憶 [(key, value), ...]，按 updated_at 倒序。"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT fact_key, fact_value FROM user_profile "
            "WHERE user_id=%s ORDER BY updated_at DESC",
            (user_id,),
        )
        return cur.fetchall()


def clear_facts(user_id: str) -> int:
    """清空該使用者所有記憶。回傳刪除筆數。"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("DELETE FROM user_profile WHERE user_id=%s", (user_id,))
        return cur.rowcount or 0
