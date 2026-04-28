"""記帳 expenses 表 CRUD。

amount 約定：
- 正數 = 支出
- 負數 = 收入（特殊分類「收入」也存負值，以利月度淨額計算）

回傳格式統一：list of (id, amount, category, description, payment_method, occurred_at)
"""
from datetime import date
from decimal import Decimal

from db.pool import get_db, logger


def add_expense(
    user_id: str,
    amount: float | Decimal,
    category: str,
    description: str | None = None,
    payment_method: str | None = None,
    occurred_at: date | str | None = None,
) -> int:
    """新增一筆。occurred_at 為 None 時取今天（DB CURRENT_DATE）。回傳新 id。"""
    sql = (
        "INSERT INTO expenses (user_id, amount, category, description, payment_method, occurred_at) "
        "VALUES (%s, %s, %s, %s, %s, COALESCE(%s, CURRENT_DATE)) RETURNING id"
    )
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(sql, (user_id, amount, category, description, payment_method, occurred_at))
        return cur.fetchone()[0]


def list_expenses(
    user_id: str,
    start_date: date | str | None = None,
    end_date: date | str | None = None,
    category: str | None = None,
    limit: int = 100,
) -> list[tuple]:
    """條件查詢，按日期 DESC, id DESC 排序。"""
    where = ["user_id = %s"]
    params: list = [user_id]
    if start_date:
        where.append("occurred_at >= %s")
        params.append(start_date)
    if end_date:
        where.append("occurred_at <= %s")
        params.append(end_date)
    if category:
        where.append("category = %s")
        params.append(category)
    sql = (
        "SELECT id, amount, category, description, payment_method, occurred_at "
        f"FROM expenses WHERE {' AND '.join(where)} "
        "ORDER BY occurred_at DESC, id DESC LIMIT %s"
    )
    params.append(limit)
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()


def get_expense(user_id: str, expense_id: int) -> tuple | None:
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, amount, category, description, payment_method, occurred_at "
            "FROM expenses WHERE id=%s AND user_id=%s",
            (expense_id, user_id),
        )
        return cur.fetchone()


def delete_expense(user_id: str, expense_id: int) -> tuple | None:
    """刪除指定 id；回傳被刪那筆（供確認訊息使用），找不到回 None。"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            "DELETE FROM expenses WHERE id=%s AND user_id=%s "
            "RETURNING id, amount, category, description, payment_method, occurred_at",
            (expense_id, user_id),
        )
        return cur.fetchone()


def summarize(
    user_id: str,
    start_date: date | str,
    end_date: date | str,
) -> dict:
    """期間彙總。回傳:
      {
        "total_expense": Decimal,    # 支出總額（amount > 0 加總）
        "total_income": Decimal,     # 收入總額（amount < 0 取絕對值加總）
        "net": Decimal,              # 支出 - 收入
        "count": int,                # 筆數
        "by_category": [(category, total, count), ...]  # 按 amount > 0 的支出彙總
      }
    """
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                COALESCE(SUM(CASE WHEN amount > 0 THEN amount END), 0) AS total_exp,
                COALESCE(SUM(CASE WHEN amount < 0 THEN -amount END), 0) AS total_inc,
                COUNT(*)
            FROM expenses
            WHERE user_id=%s AND occurred_at BETWEEN %s AND %s
            """,
            (user_id, start_date, end_date),
        )
        total_exp, total_inc, count = cur.fetchone()
        cur.execute(
            """
            SELECT category, SUM(amount) AS total, COUNT(*)
            FROM expenses
            WHERE user_id=%s AND occurred_at BETWEEN %s AND %s AND amount > 0
            GROUP BY category
            ORDER BY total DESC
            """,
            (user_id, start_date, end_date),
        )
        by_cat = cur.fetchall()
    return {
        "total_expense": total_exp or Decimal(0),
        "total_income": total_inc or Decimal(0),
        "net": (total_exp or Decimal(0)) - (total_inc or Decimal(0)),
        "count": int(count or 0),
        "by_category": [(c, float(t), int(n)) for c, t, n in by_cat],
    }
