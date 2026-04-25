"""備忘錄：slash command 與自然語言函式"""
import re

import db


def handle_note(text: str, user_id: str) -> str:
    parts = text.strip().split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        return note_list(user_id)
    if re.match(r"(刪除?|x)\s*(\d+)$", arg):
        idx = int(re.search(r"\d+", arg).group())
        return note_delete(user_id, idx)
    if arg == "清空":
        db.clear_notes(user_id)
        return "🗑 備忘錄已清空～"
    return note_add(user_id, arg)


def note_list(user_id: str) -> str:
    notes = db.get_notes(user_id)
    if not notes:
        return "📒 備忘錄是空的\n說「記下...」或 /記事 <內容> 來新增"
    lines = ["📒 備忘錄："]
    for i, (_id, content, created_at) in enumerate(notes, 1):
        time_str = (
            created_at.strftime("%m/%d %H:%M")
            if hasattr(created_at, "strftime") else str(created_at)[:16]
        )
        lines.append(f"  {i}. {content}  🕐{time_str}")
    return "\n".join(lines)


def note_add(user_id: str, content: str) -> str:
    count = db.add_note(user_id, content)
    return f"📒 已記下：「{content}」（共 {count} 則）"


def note_delete(user_id: str, index: int) -> str:
    name = db.delete_note(user_id, index)
    return f"🗑 已刪除：「{name}」" if name else "⚠️ 找不到該編號，用 /記事 查看清單"
