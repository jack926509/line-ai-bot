"""早晨簡報組合（問候 + 行程 + 待辦 + 天氣 + 節日 + 支出）"""
import logging
from datetime import datetime, date, timedelta

import requests
from zoneinfo import ZoneInfo

import db
from config import TZ_NAME, WEEKDAY_NAMES, WEATHER_CITY
from calendar_tw import get_holiday_context
from features.calendar import get_events as gcal_get_events

logger = logging.getLogger("lumio.briefing")


def _greeting() -> str:
    now = datetime.now(ZoneInfo(TZ_NAME))
    weekday = WEEKDAY_NAMES[now.weekday()]
    return f"☀️ 早安！今天是 {now.strftime('%Y/%m/%d')}（{weekday}）"


def _today_todos_block(user_id: str) -> str:
    todos = db.get_todos(user_id)
    today = date.today()
    overdue, due_today, no_date = [], [], []
    for _id, content, done, category, due_date in todos:
        if done:
            continue
        if due_date is None:
            no_date.append((category, content))
            continue
        d = due_date if hasattr(due_date, "year") else datetime.strptime(str(due_date), "%Y-%m-%d").date()
        if d < today:
            overdue.append((category, content, d))
        elif d == today:
            due_today.append((category, content))

    if not overdue and not due_today:
        return "📝 今日待辦：✨ 無到期事項"

    lines = ["📝 今日待辦："]
    for cat, content, d in overdue:
        lines.append(f"  🔴過期 {content}（{cat} · {d.month}/{d.day}）")
    for cat, content in due_today:
        lines.append(f"  🟠今天 {content}（{cat}）")
    return "\n".join(lines)


def _expense_block(user_id: str) -> str:
    """昨日支出 + 本月累計（簡短版，置於早報尾段）。"""
    try:
        today = date.today()
        yesterday = today - timedelta(days=1)
        month_start = today.replace(day=1)
        y = db.expense_summarize(user_id, yesterday, yesterday)
        m = db.expense_summarize(user_id, month_start, today)
    except Exception as e:
        logger.warning(f"支出區塊失敗: {e}")
        return ""

    if y["count"] == 0 and m["count"] == 0:
        return ""

    lines = []
    if y["count"] > 0:
        lines.append(f"💰 昨日支出 NT${float(y['total_expense']):,.0f}（{y['count']} 筆）")
    if m["count"] > 0:
        # 取前 3 大分類
        top = m["by_category"][:3]
        if top:
            cat_str = "  ".join(
                f"{cat} NT${amt:,.0f}" for cat, amt, _ in top
            )
            lines.append(f"📊 本月累計 NT${float(m['total_expense']):,.0f}")
            lines.append(f"   {cat_str}")
    return "\n".join(lines)


def _weather_block() -> str:
    try:
        resp = requests.get(
            f"https://wttr.in/{WEATHER_CITY}?format=%l:+%c+%t+%w&lang=zh",
            headers={"Accept-Charset": "utf-8"},
            timeout=5,
        )
        resp.encoding = "utf-8"
        text = resp.text.strip()
        return f"🌤 {text}" if text else ""
    except Exception as e:
        logger.warning(f"天氣抓取失敗: {e}")
        return ""


def build_morning_briefing(user_id: str) -> str:
    parts = [_greeting()]

    holiday = get_holiday_context(datetime.now(ZoneInfo(TZ_NAME))).strip()
    if holiday:
        parts.append(holiday)

    parts.append("")
    parts.append(gcal_get_events())

    parts.append("")
    parts.append(_today_todos_block(user_id))

    expense = _expense_block(user_id)
    if expense:
        parts.append("")
        parts.append(expense)

    weather = _weather_block()
    if weather:
        parts.append("")
        parts.append(weather)

    parts.append("")
    parts.append("祝今天順利～")
    return "\n".join(parts)
