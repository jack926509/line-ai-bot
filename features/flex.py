"""Flex Message 與 Postback 資料協定。

Postback data 採用 URL query string 格式，欄位簡短：
  act=<feature>.<verb>&i=<index>

例：
  act=todo.done&i=3
  act=todo.del&i=2
  act=note.del&i=1

由 main.py 的 on_postback 解析後分派回各 feature。
"""
from datetime import datetime
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from linebot.v3.messaging import FlexMessage, FlexContainer

from config import TZ_NAME

# LINE Flex carousel 上限為 12 個 bubble；本地再限制以免訊息過長
_MAX_BUBBLES = 10


def _pb(act: str, **kw) -> str:
    """組 postback data。"""
    return urlencode({"act": act, **kw})


def parse_postback(data: str) -> dict:
    """將 postback data 解析為 dict。容錯：格式錯誤回空 dict。"""
    if not data:
        return {}
    out: dict[str, str] = {}
    for piece in data.split("&"):
        if "=" not in piece:
            continue
        k, _, v = piece.partition("=")
        out[k] = v
    return out


def _due_label(due_date) -> tuple[str, str]:
    """回傳 (顯示文字, 顏色)；無到期日回 ("", "")"""
    if not due_date:
        return "", ""
    today = datetime.now(ZoneInfo(TZ_NAME)).date()
    d = due_date if hasattr(due_date, "year") else datetime.strptime(str(due_date), "%Y-%m-%d").date()
    diff = (d - today).days
    if diff < 0:
        return f"過期 {-diff} 天", "#D32F2F"
    if diff == 0:
        return "今天到期", "#D32F2F"
    if diff == 1:
        return "明天到期", "#F57C00"
    return f"{d.month}/{d.day}", "#666666"


def _todo_bubble(index: int, content: str, done: bool, category: str, due_date) -> dict:
    due_text, due_color = _due_label(due_date)
    header_text = f"#{index}  {category}"
    body_contents: list[dict] = [
        {"type": "text", "text": content, "wrap": True, "weight": "bold", "size": "md",
         "color": "#888888" if done else "#111111",
         "decoration": "line-through" if done else "none"},
    ]
    if due_text:
        body_contents.append({
            "type": "text", "text": "📅 " + due_text, "size": "sm", "color": due_color,
            "margin": "sm",
        })
    if done:
        body_contents.append({
            "type": "text", "text": "✅ 已完成", "size": "sm", "color": "#4CAF50", "margin": "sm",
        })

    footer_buttons: list[dict] = []
    if not done:
        footer_buttons.append({
            "type": "button", "style": "primary", "color": "#4CAF50", "height": "sm",
            "action": {"type": "postback", "label": "✓ 完成",
                       "data": _pb("todo.done", i=index),
                       "displayText": f"完成第 {index} 項"},
        })
    footer_buttons.append({
        "type": "button", "style": "secondary", "height": "sm",
        "action": {"type": "postback", "label": "🗑 刪除",
                   "data": _pb("todo.del", i=index),
                   "displayText": f"刪除第 {index} 項"},
    })

    return {
        "type": "bubble", "size": "kilo",
        "header": {
            "type": "box", "layout": "vertical", "paddingAll": "md",
            "backgroundColor": "#F5F5F5",
            "contents": [{"type": "text", "text": header_text, "size": "sm", "color": "#666666"}],
        },
        "body": {
            "type": "box", "layout": "vertical", "paddingAll": "md", "spacing": "sm",
            "contents": body_contents,
        },
        "footer": {
            "type": "box", "layout": "vertical", "spacing": "sm",
            "contents": footer_buttons,
        },
    }


def todo_carousel(todos: list) -> FlexMessage | None:
    """todos 為 db.get_todos 結果：list of (id, content, done, category, due_date)。
    回傳 FlexMessage；空清單回 None 由呼叫端走文字 fallback。"""
    if not todos:
        return None
    bubbles = [
        _todo_bubble(i, content, done, category, due_date)
        for i, (_id, content, done, category, due_date) in enumerate(todos[:_MAX_BUBBLES], 1)
    ]
    container = {"type": "carousel", "contents": bubbles}
    alt = f"📝 待辦清單 {len(todos)} 項" + ("" if len(todos) <= _MAX_BUBBLES
                                              else f"（顯示前 {_MAX_BUBBLES}）")
    return FlexMessage(alt_text=alt, contents=FlexContainer.from_dict(container))


def _note_bubble(index: int, content: str, created_at) -> dict:
    time_str = (
        created_at.strftime("%m/%d %H:%M")
        if hasattr(created_at, "strftime") else str(created_at)[:16]
    )
    return {
        "type": "bubble", "size": "kilo",
        "header": {
            "type": "box", "layout": "vertical", "paddingAll": "md",
            "backgroundColor": "#F5F5F5",
            "contents": [{"type": "text", "text": f"#{index}  🕐 {time_str}",
                          "size": "sm", "color": "#666666"}],
        },
        "body": {
            "type": "box", "layout": "vertical", "paddingAll": "md",
            "contents": [{"type": "text", "text": content, "wrap": True, "size": "md"}],
        },
        "footer": {
            "type": "box", "layout": "vertical",
            "contents": [{
                "type": "button", "style": "secondary", "height": "sm",
                "action": {"type": "postback", "label": "🗑 刪除",
                           "data": _pb("note.del", i=index),
                           "displayText": f"刪除第 {index} 則"},
            }],
        },
    }


def note_carousel(notes: list) -> FlexMessage | None:
    """notes 為 db.get_notes 結果：list of (id, content, created_at)。"""
    if not notes:
        return None
    bubbles = [
        _note_bubble(i, content, created_at)
        for i, (_id, content, created_at) in enumerate(notes[:_MAX_BUBBLES], 1)
    ]
    container = {"type": "carousel", "contents": bubbles}
    alt = f"📒 備忘錄 {len(notes)} 則"
    return FlexMessage(alt_text=alt, contents=FlexContainer.from_dict(container))


# ── 記帳 Flex ─────────────────────────────────────


def _expense_bubble(eid: int, amount, category: str, description, payment_method,
                    occurred_at, emoji: str) -> dict:
    amt = float(amount)
    is_income = amt < 0
    amount_color = "#388E3C" if is_income else "#D32F2F"
    amount_text = (f"+NT${-amt:,.0f}" if is_income else f"NT${amt:,.0f}")
    occ_text = occurred_at.strftime("%m/%d") if hasattr(occurred_at, "strftime") else str(occurred_at)[:10]
    body_contents: list[dict] = [
        {"type": "text", "text": amount_text, "size": "xxl", "weight": "bold",
         "color": amount_color},
        {"type": "text", "text": f"{emoji} {category}", "size": "md", "color": "#333333",
         "margin": "sm"},
    ]
    if description:
        body_contents.append({"type": "text", "text": description, "wrap": True,
                              "size": "sm", "color": "#666666", "margin": "xs"})
    meta_parts = [occ_text]
    if payment_method:
        meta_parts.append(payment_method)
    body_contents.append({"type": "text", "text": "  ·  ".join(meta_parts),
                          "size": "xs", "color": "#999999", "margin": "md"})
    return {
        "type": "bubble", "size": "kilo",
        "header": {
            "type": "box", "layout": "vertical", "paddingAll": "md",
            "backgroundColor": "#F5F5F5",
            "contents": [{"type": "text", "text": f"#{eid}", "size": "sm", "color": "#666666"}],
        },
        "body": {
            "type": "box", "layout": "vertical", "paddingAll": "md", "spacing": "xs",
            "contents": body_contents,
        },
        "footer": {
            "type": "box", "layout": "vertical",
            "contents": [{
                "type": "button", "style": "secondary", "height": "sm",
                "action": {"type": "postback", "label": "🗑 刪除",
                           "data": _pb("expense.del", id=eid),
                           "displayText": f"刪除記帳 #{eid}"},
            }],
        },
    }


def expense_carousel(rows: list, title: str) -> FlexMessage | None:
    """rows 為 db.list_expenses 結果。"""
    if not rows:
        return None
    from features.expense import _emoji  # 避免頂層循環匯入
    total_amt = sum(float(r[1]) for r in rows)
    summary_text = f"{title}  共 {len(rows)} 筆  小計 NT${total_amt:,.0f}"
    bubbles = [
        _expense_bubble(eid, amt, cat, desc, pm, dt, _emoji(cat))
        for (eid, amt, cat, desc, pm, dt) in rows[:_MAX_BUBBLES]
    ]
    container = {"type": "carousel", "contents": bubbles}
    return FlexMessage(alt_text=summary_text, contents=FlexContainer.from_dict(container))


def _bar_box(pct: float, color: str) -> dict:
    """水平百分比 bar（基於 box flex 屬性實現）。"""
    pct = max(0.0, min(100.0, pct))
    if pct < 1:
        # 避免 flex=0 排版怪異
        return {
            "type": "box", "layout": "horizontal", "height": "8px",
            "contents": [{"type": "box", "layout": "vertical", "flex": 100,
                          "backgroundColor": "#EEEEEE", "contents": []}],
        }
    return {
        "type": "box", "layout": "horizontal", "height": "8px", "spacing": "none",
        "contents": [
            {"type": "box", "layout": "vertical", "flex": int(round(pct)),
             "backgroundColor": color, "contents": []},
            {"type": "box", "layout": "vertical", "flex": max(1, 100 - int(round(pct))),
             "backgroundColor": "#EEEEEE", "contents": []},
        ],
    }


def expense_summary_bubble(summary: dict, period_label: str, sd, ed) -> FlexMessage:
    """summary 為 db.expense_summarize 回傳的 dict。"""
    from features.expense import CATEGORY_EMOJI
    total_exp = float(summary["total_expense"])
    total_inc = float(summary["total_income"])
    net = float(summary["net"])
    count = summary["count"]
    by_cat = summary["by_category"]

    body_contents: list[dict] = [
        {"type": "text", "text": f"📊 {period_label} 支出統計", "weight": "bold", "size": "lg"},
        {"type": "text", "text": f"{sd} ~ {ed}", "size": "xs", "color": "#999999"},
        {"type": "separator", "margin": "md"},
        {"type": "box", "layout": "horizontal", "margin": "md",
         "contents": [
             {"type": "text", "text": "💸 支出", "size": "sm", "color": "#666666", "flex": 2},
             {"type": "text", "text": f"NT${total_exp:,.0f}", "size": "sm",
              "weight": "bold", "color": "#D32F2F", "align": "end", "flex": 5},
         ]},
        {"type": "box", "layout": "horizontal",
         "contents": [
             {"type": "text", "text": f"  ({count} 筆)", "size": "xs", "color": "#999999"},
         ]},
    ]
    if total_inc > 0:
        body_contents.append({
            "type": "box", "layout": "horizontal", "margin": "sm",
            "contents": [
                {"type": "text", "text": "💰 收入", "size": "sm", "color": "#666666", "flex": 2},
                {"type": "text", "text": f"NT${total_inc:,.0f}", "size": "sm",
                 "weight": "bold", "color": "#388E3C", "align": "end", "flex": 5},
            ],
        })
        body_contents.append({
            "type": "box", "layout": "horizontal", "margin": "sm",
            "contents": [
                {"type": "text", "text": "📈 淨額", "size": "sm", "color": "#666666", "flex": 2},
                {"type": "text", "text": f"NT${net:,.0f}", "size": "sm",
                 "weight": "bold", "align": "end", "flex": 5,
                 "color": "#D32F2F" if net > 0 else "#388E3C"},
            ],
        })

    if by_cat:
        body_contents.append({"type": "separator", "margin": "lg"})
        body_contents.append({"type": "text", "text": "分類占比", "size": "sm",
                              "color": "#888888", "margin": "md"})
        denom = total_exp or 1.0
        # 顏色循環（給每個分類一個明顯的色）
        colors = ["#FF7043", "#42A5F5", "#AB47BC", "#26A69A", "#FFA726",
                  "#5C6BC0", "#EF5350", "#66BB6A", "#FFCA28", "#8D6E63"]
        for i, (cat, amount, _n) in enumerate(by_cat[:8]):
            pct = amount / denom * 100
            emoji = CATEGORY_EMOJI.get(cat, "📦")
            body_contents.append({
                "type": "box", "layout": "vertical", "margin": "md", "spacing": "xs",
                "contents": [
                    {"type": "box", "layout": "horizontal",
                     "contents": [
                         {"type": "text", "text": f"{emoji} {cat}", "size": "sm", "flex": 3},
                         {"type": "text", "text": f"{pct:.1f}%  NT${amount:,.0f}",
                          "size": "xs", "color": "#666666", "align": "end", "flex": 5},
                     ]},
                    _bar_box(pct, colors[i % len(colors)]),
                ],
            })

    bubble = {
        "type": "bubble", "size": "mega",
        "body": {
            "type": "box", "layout": "vertical", "paddingAll": "lg", "spacing": "xs",
            "contents": body_contents,
        },
    }
    return FlexMessage(alt_text=f"📊 {period_label}支出 NT${total_exp:,.0f}",
                       contents=FlexContainer.from_dict(bubble))
