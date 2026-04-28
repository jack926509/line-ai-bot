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
