"""使用者長期記憶（profile_remember / profile_list / profile_forget）"""
import db


def remember(user_id: str, key: str, value: str) -> str:
    ok, msg = db.profile_remember(user_id, key, value)
    if not ok:
        return f"⚠️ {msg}"
    return f"🧠 {msg}：「{key}」= 「{value}」"


def forget(user_id: str, key: str) -> str:
    if db.profile_forget(user_id, key):
        return f"🧠 已忘記：「{key}」"
    return f"⚠️ 找不到 key「{key}」（用 profile_list 查看）"


def list_memory(user_id: str) -> str:
    facts = db.profile_list(user_id)
    if not facts:
        return "🧠 暫無長期記憶（會在對話中自然累積）"
    lines = ["🧠 我記得這些事："]
    for k, v in facts:
        lines.append(f"- {k}：{v}")
    return "\n".join(lines)
