"""待辦事項：slash command 與自然語言函式"""
import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import db
from config import TZ_NAME


def handle_todo(text: str, user_id: str) -> str:
    t = text.strip()
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
    if arg == "清空":
        db.clear_todos(user_id)
        return "🗑 待辦清單已清空～"

    content, category, due_date = _parse_todo_input(arg)
    return todo_add(user_id, content, category=category, due_date=due_date)


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
            # 若指定的 (月, 日) 已過今天則自動推到明年
            today = now.date()
            try:
                target = date(today.year, mo, d)
            except ValueError:
                return content.strip(), category, None
            if target < today:
                target = date(today.year + 1, mo, d)
            due_date = target.strftime("%Y-%m-%d")
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
