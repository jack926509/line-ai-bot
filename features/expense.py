"""記帳：slash 指令、Claude 工具入口、彙總文字格式化。

設計約定：
- amount > 0：支出
- amount < 0：收入（分類預設「收入」）
- 預設分類見 CATEGORIES，老闆任意自訂分類也接受（Claude 會學習常用詞彙）
- 預設付款方式見 PAYMENT_METHODS
"""
import logging
import re
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

import db
from config import TZ_NAME

logger = logging.getLogger("lumio.expense")
_TZ = ZoneInfo(TZ_NAME)


# 預設分類（個人化情境的台灣常見項目）— Claude 會用這個清單做意圖分類
CATEGORIES = [
    "餐飲", "交通", "購物", "娛樂", "醫療",
    "生活", "家庭", "教育", "投資", "收入", "其他",
]

CATEGORY_EMOJI = {
    "餐飲": "🍱", "交通": "🚗", "購物": "🛍️", "娛樂": "🎮", "醫療": "💊",
    "生活": "🏠", "家庭": "👨‍👩‍👧", "教育": "📚", "投資": "📈", "收入": "💰", "其他": "📦",
}

PAYMENT_METHODS = ["現金", "信用卡", "Line Pay", "悠遊卡", "街口", "ATM"]


def today_tw() -> date:
    """台北時區的今日日期。供本模組與外部（如 main.py）共用。"""
    return datetime.now(_TZ).date()


def period_range(period: str, today: date | None = None) -> tuple[date, date]:
    """將期間關鍵字（today/yesterday/week/month/last_month/year）換算為 (start, end)。

    未知 period 預設回今天 ~ 今天。供 expense_summary 與 main.py Flex 統計共用。
    """
    t = today or today_tw()
    if period == "today":
        return t, t
    if period == "yesterday":
        d = t - timedelta(days=1)
        return d, d
    if period == "week":
        return t - timedelta(days=t.weekday()), t
    if period == "month":
        return t.replace(day=1), t
    if period == "last_month":
        ed = t.replace(day=1) - timedelta(days=1)
        return ed.replace(day=1), ed
    if period == "year":
        return t.replace(month=1, day=1), t
    return t, t


def _emoji(category: str) -> str:
    return CATEGORY_EMOJI.get(category, "📦")


def _fmt_amount(amount) -> str:
    """格式化金額：千分位 + NT$。負數（收入）顯示為 +xxx。"""
    a = float(amount)
    if a < 0:
        return f"+NT${-a:,.0f}"
    return f"NT${a:,.0f}"


def _parse_amount(text: str) -> Decimal | None:
    try:
        return Decimal(str(text).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


# ── Claude tool 入口 ──────────────────────────────


def expense_add(
    user_id: str,
    amount: float,
    category: str,
    description: str | None = None,
    payment_method: str | None = None,
    occurred_at: str | None = None,
) -> str:
    """新增一筆。occurred_at 為 YYYY-MM-DD 字串或 None（=今天）。
    若分類為「收入」且 amount > 0，自動轉負數。"""
    amt = _parse_amount(amount)
    if amt is None:
        return f"⚠️ 金額無效：{amount}"
    if amt == 0:
        return "⚠️ 金額不可為 0"
    if category == "收入" and amt > 0:
        amt = -amt
    occ: date | None = None
    if occurred_at:
        try:
            occ = datetime.strptime(occurred_at, "%Y-%m-%d").date()
        except ValueError:
            return f"⚠️ 日期格式錯誤：{occurred_at}（需 YYYY-MM-DD）"
    eid = db.add_expense(user_id, amt, category, description, payment_method, occ)
    parts = [f"💰 已記 {_emoji(category)} {category} {_fmt_amount(amt)}"]
    if description:
        parts.append(f"（{description}")
        if payment_method:
            parts.append(f"，{payment_method}")
        parts.append("）")
    elif payment_method:
        parts.append(f"（{payment_method}）")
    parts.append(f"\nid={eid}")
    return "".join(parts)


def expense_query(
    user_id: str,
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
) -> str:
    """條件查詢。日期為 YYYY-MM-DD 字串。皆未指定時取今天。"""
    today = today_tw()
    sd = _parse_date(start_date) or today
    ed = _parse_date(end_date) or today
    if ed < sd:
        sd, ed = ed, sd
    rows = db.list_expenses(user_id, sd, ed, category, limit=50)
    if not rows:
        scope = f"{sd}~{ed}" + (f" {category}" if category else "")
        return f"📭 {scope} 沒有紀錄"
    lines = [f"💰 {sd} ~ {ed}" + (f"（{category}）" if category else "")]
    total = Decimal(0)
    for _id, amt, cat, desc, pm, dt in rows:
        total += amt
        line = f"  [{_id}] {dt}  {_emoji(cat)}{cat}  {_fmt_amount(amt)}"
        if desc:
            line += f"  {desc}"
        if pm:
            line += f"  ({pm})"
        lines.append(line)
    lines.append(f"\n小計（{len(rows)} 筆）：{_fmt_amount(total)}")
    return "\n".join(lines)


def expense_summary(user_id: str, period: str = "month") -> str:
    """彙總統計。period: today / yesterday / week / month / last_month / year。"""
    if period not in ("today", "yesterday", "week", "month", "last_month", "year"):
        return f"⚠️ 不支援的期間：{period}"
    sd, ed = period_range(period)
    return _format_summary(user_id, sd, ed, label_period(period))


def expense_delete(user_id: str, expense_id: int) -> str:
    row = db.delete_expense(user_id, expense_id)
    if not row:
        return f"⚠️ 找不到 id={expense_id}（用 expense_query 查看）"
    _id, amt, cat, desc, _pm, dt = row
    return f"🗑 已刪除 [{_id}] {dt} {_emoji(cat)}{cat} {_fmt_amount(amt)}" + (f"（{desc}）" if desc else "")


# ── 內部 helper ──────────────────────────────────


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def label_period(period: str) -> str:
    return {
        "today": "今日", "yesterday": "昨日", "week": "本週",
        "month": "本月", "last_month": "上月", "year": "今年",
    }.get(period, period)


def _format_summary(user_id: str, sd: date, ed: date, label: str) -> str:
    s = db.expense_summarize(user_id, sd, ed)
    if s["count"] == 0:
        return f"📭 {label}（{sd}~{ed}）沒有紀錄"
    lines = [f"📊 {label} 支出統計（{sd}~{ed}）"]
    lines.append(f"━━━━━━━━━━━")
    lines.append(f"💸 支出：{_fmt_amount(s['total_expense'])}（{s['count']} 筆）")
    if s["total_income"] > 0:
        lines.append(f"💰 收入：NT${float(s['total_income']):,.0f}")
        lines.append(f"📈 淨額：NT${float(s['net']):,.0f}")
    if s["by_category"]:
        lines.append("")
        lines.append("分類占比：")
        total_exp = float(s["total_expense"]) or 1.0
        for cat, amount, count in s["by_category"]:
            pct = amount / total_exp * 100
            bar = _bar(pct)
            lines.append(f"  {_emoji(cat)} {cat:<4} {bar} {pct:5.1f}%  NT${amount:,.0f}（{count}）")
    return "\n".join(lines)


def _bar(pct: float, width: int = 10) -> str:
    filled = max(0, min(width, int(pct / 100 * width)))
    return "█" * filled + "░" * (width - filled)


# ── Slash command handler ───────────────────────


_DELETE_RE = re.compile(r"^(刪除?|x)\s*(\d+)$")
_QUERY_RE = re.compile(r"^查\s+(\S+)$")


def handle_expense(text: str, user_id: str) -> str:
    """處理 /記帳 子指令；列表 / 月統計由 main.py 的 _expense_response 走 Flex。"""
    parts = text.strip().split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        # 由 main.py 的 _expense_response 改走 Flex；這裡走文字 fallback
        return expense_query(user_id)
    if arg in ("月", "本月"):
        return expense_summary(user_id, "month")
    if arg in ("上月",):
        return expense_summary(user_id, "last_month")
    if arg in ("週", "本週"):
        return expense_summary(user_id, "week")
    if arg in ("年", "今年"):
        return expense_summary(user_id, "year")
    if arg == "昨日":
        return expense_summary(user_id, "yesterday")
    if arg == "今日":
        return expense_summary(user_id, "today")
    m = _DELETE_RE.match(arg)
    if m:
        return expense_delete(user_id, int(m.group(2)))
    m = _QUERY_RE.match(arg)
    if m:
        return expense_query(user_id, category=m.group(1))
    if arg == "清單":
        return expense_query(user_id)
    return (
        "💰 記帳指令：\n"
        "/記帳            今日支出\n"
        "/記帳 月         本月統計\n"
        "/記帳 上月       上月統計\n"
        "/記帳 週         本週統計\n"
        "/記帳 查 餐飲   篩選分類\n"
        "/記帳 刪 5      刪第 5 筆\n\n"
        "也可直接說「午餐 120」「咖啡 150 刷卡」自然記帳"
    )
