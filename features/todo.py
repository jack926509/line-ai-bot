"""待辦事項 & 備忘錄：slash command 處理 + 自然語言 dispatch 函式"""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import db
from config import TZ_NAME


# ── Slash command handlers ────────────────────────


def handle_reset_memory(user_id: str) -> str:
    db.clear_history(user_id)
    return "🔄 對話記憶已清除，Lumio 會重新認識你～\n（待辦與備忘不受影響）"


def handle_todo(text: str, user_id: str) -> str:
    t = text.strip()
    # 支援 /t 短別名
    if t.startswith("/t "):
        t = "/待辦 " + t[3:]
    elif t == "/t":
        t = "/待辦"

    parts = t.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        return _show_todos(user_id)
    if re.match(r"(完成|v)\s*(\d+)$", arg):
        idx = int(re.search(r"\d+", arg).group())
        return todo_complete(user_id, idx)
    if re.match(r"(刪除?|x)\s*(\d+)$", arg):
        idx = int(re.search(r"\d+", arg).group())
        return todo_delete(user_id, idx)
    if arg in ("清空",):
        db.clear_todos(user_id)
        return "🗑 待辦清單已清空～"

    content, category, due_date = _parse_todo_input(arg)
    return todo_add(user_id, content, category=category, due_date=due_date)


def handle_note(text: str, user_id: str) -> str:
    t = text.strip()
    parts = t.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        return note_list(user_id)
    if re.match(r"(刪除?|x)\s*(\d+)$", arg):
        idx = int(re.search(r"\d+", arg).group())
        return note_delete(user_id, idx)
    if arg in ("清空",):
        db.clear_notes(user_id)
        return "🗑 備忘錄已清空～"

    return note_add(user_id, arg)


def handle_help() -> str:
    return (
        "💕 Lumio 使用說明\n"
        "━━━━━━━━━━━\n"
        "💬 直接說話 → 什麼都能聊\n"
        "🖼 傳圖片 → AI 圖片分析\n"
        "📄 傳檔案 → PDF/TXT/MD/CSV 摘要\n"
        "🔗 貼網址 → 自動摘要重點\n"
        "━━━━━━━━━━━\n"
        "☀️ 推播\n"
        "  /簡報            立即查看早晨簡報\n"
        "  /狀態            訂閱與資料統計\n"
        "  /簡報 開|關      開關每日簡報\n"
        "━━━━━━━━━━━\n"
        "📅 行事曆\n"
        "  「排明天3點開會」\n"
        "  「把會議改到下午5點」\n"
        "  /日曆 / /日曆 明天|本週|即將|4/30\n"
        "━━━━━━━━━━━\n"
        "📝 待辦\n"
        "  「幫我記下買牛奶」\n"
        "  /待辦 /t         查看\n"
        "  /待辦 <內容>     新增\n"
        "  /待辦 完成 1     勾選\n"
        "  /待辦 刪 1       刪除\n"
        "📒 備忘\n"
        "  /記事 / /記事 <內容> / /記事 刪 1\n"
        "━━━━━━━━━━━\n"
        "🔗 摘要\n"
        "  /摘要 <網址>     立即摘要任何網址\n"
        "━━━━━━━━━━━\n"
        "/reset  清除對話記憶\n"
        "/h      顯示說明"
    )


# ── 自然語言工具函式（供 tools.py dispatch 呼叫）──


def todo_list(user_id: str) -> str:
    return _show_todos(user_id)


def todo_add(user_id: str, content: str, category: str = "一般", due_date: str | None = None) -> str:
    count = db.add_todo(user_id, content, category=category, due_date=due_date)
    result = f"📝 已新增：「{content}」"
    if category != "一般":
        result += f"  📂{category}"
    if due_date:
        result += f"  📅{due_date}"
    result += f"\n共 {count} 項待辦"
    return result


def todo_complete(user_id: str, index: int) -> str:
    name = db.complete_todo(user_id, index)
    return f"✅ 完成！「{name}」" if name else "⚠️ 找不到該編號，用 /待辦 查看清單"


def todo_delete(user_id: str, index: int) -> str:
    name = db.delete_todo(user_id, index)
    return f"🗑 已刪除「{name}」" if name else "⚠️ 找不到該編號，用 /待辦 查看清單"


def note_list(user_id: str) -> str:
    notes = db.get_notes(user_id)
    if not notes:
        return "📒 備忘錄是空的\n說「記下...」或 /記事 <內容> 來新增"
    lines = ["📒 備忘錄："]
    for i, (_id, content, created_at) in enumerate(notes, 1):
        time_str = created_at.strftime("%m/%d %H:%M") if hasattr(created_at, "strftime") else str(created_at)[:16]
        lines.append(f"  {i}. {content}  🕐{time_str}")
    return "\n".join(lines)


def note_add(user_id: str, content: str) -> str:
    count = db.add_note(user_id, content)
    return f"📒 已記下：「{content}」（共 {count} 則）"


def note_delete(user_id: str, index: int) -> str:
    name = db.delete_note(user_id, index)
    return f"🗑 已刪除：「{name}」" if name else "⚠️ 找不到該編號，用 /記事 查看清單"


# ── 內部輔助 ──────────────────────────────────────


def _parse_todo_input(text: str) -> tuple[str, str, str | None]:
    content, category, due_date = text, "一般", None

    m = re.match(r"#(\S+)\s+", content)
    if m:
        category = m.group(1)
        content = content[m.end():]

    now = datetime.now(ZoneInfo(TZ_NAME))
    for prefix, delta in [("今天 ", 0), ("明天 ", 1), ("後天 ", 2)]:
        if content.startswith(prefix):
            due_date = (now + timedelta(days=delta)).strftime("%Y-%m-%d")
            content = content[len(prefix):]
            break
    else:
        dm = re.match(r"(\d{1,2})/(\d{1,2})\s+", content)
        if dm:
            mo, d = int(dm.group(1)), int(dm.group(2))
            year = now.year if mo >= now.month else now.year + 1
            due_date = f"{year}-{mo:02d}-{d:02d}"
            content = content[dm.end():]

    return content.strip(), category, due_date


def _show_todos(user_id: str) -> str:
    todos = db.get_todos(user_id)
    if not todos:
        return (
            "📝 待辦清單是空的\n\n"
            "說「幫我記下買牛奶」或\n"
            "/待辦 #工作 4/5 準備簡報"
        )
    lines, current_cat = [], None
    for i, (_id, content, done, category, due_date) in enumerate(todos, 1):
        if category != current_cat:
            current_cat = category
            lines.append(f"\n📂 {category}")
        mark = "✅" if done else "⬜"
        due_str = ""
        if due_date:
            today = datetime.now(ZoneInfo(TZ_NAME)).date()
            d = due_date if hasattr(due_date, "year") else datetime.strptime(str(due_date), "%Y-%m-%d").date()
            diff = (d - today).days
            due_str = (" 🔴過期" if diff < 0 else " 🔴今天" if diff == 0
                       else " 🟡明天" if diff == 1 else f" 📅{d.month}/{d.day}")
        lines.append(f"  {mark} {i}. {content}{due_str}")
    return "📝 待辦清單：" + "\n".join(lines)
