"""匯出待辦 / 備忘 / 記帳 / 對話為單則純文字訊息（Markdown 純化版）。

對話歷史受 db.MAX_HISTORY 限制（預設 12）；記帳支援指定天數。
LINE 文字訊息上限 5000 字，超過時截斷並提示。
"""
from datetime import timedelta
from decimal import Decimal

import db
from features.expense import _emoji, _fmt_amount, today_tw


_MAX_CHARS = 4500
_MAX_HISTORY_LINE = 120


def export_summary(user_id: str, days: int = 7) -> str:
    days = max(1, min(days, 30))
    today = today_tw()
    since = today - timedelta(days=days - 1)

    parts: list[str] = [
        f"📦 Lumio 匯出（{since} ~ {today}，{days} 天）",
        "━━━━━━━━━━━",
    ]

    todos = db.get_todos(user_id)
    if todos:
        parts.append("\n📝 待辦清單")
        for i, (content, category, done) in enumerate(todos, 1):
            mark = "✅" if done else "⬜"
            parts.append(f"  {mark} {i}. [{category}] {content}")

    notes = db.get_notes(user_id)
    if notes:
        parts.append("\n📒 備忘")
        for i, content in enumerate(notes, 1):
            parts.append(f"  {i}. {content}")

    expenses = db.list_expenses(user_id, since, today, limit=100)
    if expenses:
        parts.append(f"\n💰 記帳（{since} ~ {today}）")
        total = Decimal(0)
        for _id, amt, cat, desc, pm, dt in expenses:
            total += amt
            line = f"  {dt} {_emoji(cat)}{cat} {_fmt_amount(amt)}"
            if desc:
                line += f"  {desc}"
            if pm:
                line += f"  ({pm})"
            parts.append(line)
        parts.append(f"  小計：{_fmt_amount(total)}（{len(expenses)} 筆）")

    history = db.get_history(user_id)
    if history:
        parts.append(f"\n💬 對話記憶（最近 {len(history)} 則）")
        for h in history:
            role = "🙋" if h["role"] == "user" else "🤖"
            text = _flatten_content(h.get("content"))
            text = text.replace("\n", " ").strip()
            if len(text) > _MAX_HISTORY_LINE:
                text = text[:_MAX_HISTORY_LINE] + "…"
            parts.append(f"  {role} {text}")

    if len(parts) <= 2:
        parts.append("\n（本期間尚無任何紀錄）")

    out = "\n".join(parts)
    if len(out) > _MAX_CHARS:
        out = out[:_MAX_CHARS] + f"\n\n…（超出長度上限，已截斷至 {_MAX_CHARS} 字）"
    return out


def _flatten_content(content) -> str:
    """對話 content 可能是 str 或 multimodal block list。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts: list[str] = []
        for b in content:
            if isinstance(b, dict):
                if b.get("type") == "text":
                    texts.append(b.get("text", ""))
                elif b.get("type") == "image":
                    texts.append("[圖片]")
                elif b.get("type") == "document":
                    texts.append("[文件]")
        return " ".join(texts)
    return str(content)
