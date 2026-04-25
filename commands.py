"""指令處理：所有 /command 的邏輯"""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import db
from config import anthropic_client, CLAUDE_MODEL, CLAUDE_MODEL_LIGHT, TZ_NAME
from prompts import SYSTEM_PROMPT, NO_MARKDOWN_SUFFIX
from services import web_search


def handle_command(text: str) -> str | None:
    """統一指令分派，回傳回覆文字；非指令回傳 None"""
    t = text.strip()

    if t.startswith("/日曆") or t.startswith("/cal"):
        return _handle_cal(t)

    if t.startswith("/旅遊") or t.startswith("/travel"):
        return _handle_trip(t)

    if t.startswith("/搜尋"):
        return _handle_search(t)

    if t.startswith("/天氣"):
        return _handle_weather(t)

    if t.startswith("/翻譯"):
        return _handle_translate(t)

    if t.startswith("/摘要"):
        return _handle_summary(t)

    if t.startswith("/郵件"):
        return _handle_email(t)

    if t.startswith("/決策"):
        return _handle_decide(t)

    if t in ("/加油",):
        return _handle_motivate()

    if t in ("/help", "/h"):
        return _handle_help()

    return None


# ── 個別指令實作 ──────────────────────────────


def handle_reset_memory(user_id: str) -> str:
    db.clear_history(user_id)
    return "🔄 對話記憶已清除，Lumio 會重新認識你～\n（待辦與備忘不受影響）"


def handle_todo(text: str, user_id: str) -> str:
    t = text.strip()
    parts = t.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        return _show_todos(user_id)

    if re.match(r"(完成|v)\s*(\d+)$", arg):
        n = re.search(r"\d+", arg).group()
        return _complete_todo(f"完成 {n}", user_id)

    if re.match(r"(刪除?|x)\s*(\d+)$", arg):
        n = re.search(r"\d+", arg).group()
        return _delete_todo(f"刪除 {n}", user_id)

    if arg in ("清空", "clear"):
        db.clear_todos(user_id)
        return "🗑 待辦清單已清空～"

    content, category, due_date = _parse_todo_input(arg)
    count = db.add_todo(user_id, content, category=category, due_date=due_date)
    result = f"📝 已新增：「{content}」"
    if category != "一般":
        result += f"  📂{category}"
    if due_date:
        result += f"  📅{due_date}"
    result += f"\n共 {count} 項待辦"
    return result


def handle_note(text: str, user_id: str) -> str:
    t = text.strip()
    parts = t.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        notes = db.get_notes(user_id)
        if not notes:
            return "📒 備忘錄是空的～\n用法：/記事 客戶說預算上限500萬"
        lines = ["📒 備忘錄："]
        for i, (_id, content, created_at) in enumerate(notes, 1):
            time_str = created_at.strftime("%m/%d %H:%M") if hasattr(created_at, "strftime") else str(created_at)[:16]
            lines.append(f"  {i}. {content}  🕐{time_str}")
        return "\n".join(lines)

    if re.match(r"(刪除?|x)\s*(\d+)$", arg):
        n = re.search(r"\d+", arg).group()
        try:
            name = db.delete_note(user_id, int(n))
            return f"🗑 已刪除：「{name}」" if name else "⚠️ 編號不對，用 /記事 查看清單"
        except (ValueError, IndexError):
            return "⚠️ 用法：/記事 刪 1"

    if arg in ("清空",):
        db.clear_notes(user_id)
        return "🗑 備忘錄已清空～"

    count = db.add_note(user_id, arg)
    return f"📒 已記下：「{arg}」（共 {count} 則）"


# ── 內部輔助 ──────────────────────────────────


def _claude(system: str, user_msg: str, max_tokens: int = 500) -> str:
    resp = anthropic_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return resp.content[0].text


def _claude_light(system: str, user_msg: str, max_tokens: int = 300) -> str:
    resp = anthropic_client.messages.create(
        model=CLAUDE_MODEL_LIGHT,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return resp.content[0].text


def _handle_search(t: str) -> str:
    parts = t.split(maxsplit=1)
    if len(parts) < 2:
        return "🔍 用法：/搜尋 台積電最新股價"
    query = parts[1]
    try:
        result = web_search(query)
        text = _claude(
            "你是大老闆的貼心秘書 Lumio，整理搜尋結果給老闆。"
            "格式：①一句話結論 ②3~5個重點 ③重要來源連結。"
            f"繁體中文，語氣溫暖專業。{NO_MARKDOWN_SUFFIX}",
            f"搜尋「{query}」：\n\n{result}",
            max_tokens=1000,
        )
        return f"🔍 搜尋結果\n\n{text}"
    except Exception as e:
        return f"⚠️ 搜尋失敗：{e}"


def _handle_weather(t: str) -> str:
    from services import get_weather
    parts = t.split()
    city = parts[1] if len(parts) > 1 else "Taipei"
    result = get_weather(city)
    return f"🌤 {result}" if result else "⚠️ 無法取得天氣，請稍後再試"


def _handle_translate(t: str) -> str:
    parts = t.split(maxsplit=1)
    if len(parts) < 2:
        return "🌐 用法：/翻譯 Hello\n（自動中英互譯）"
    try:
        text = _claude_light(
            "翻譯助手：中文→英文，英文→中文。只回覆翻譯結果。",
            parts[1],
        )
        return f"🌐 {text}"
    except Exception:
        return "⚠️ 翻譯失敗，請稍後再試"


def _handle_summary(t: str) -> str:
    parts = t.split(maxsplit=1)
    if len(parts) < 2:
        return "📋 用法：/摘要 <貼入長文>"
    try:
        text = _claude(
            "精簡摘要：①一句話總結 ②3~5個重點 ③需老闆注意的事項。"
            f"繁體中文，語氣專業溫暖。{NO_MARKDOWN_SUFFIX}",
            parts[1],
            max_tokens=600,
        )
        return f"📋 摘要\n\n{text}"
    except Exception:
        return "⚠️ 摘要失敗，請稍後再試"


def _handle_email(t: str) -> str:
    parts = t.split(maxsplit=1)
    if len(parts) < 2:
        return "📧 用法：/郵件 回覆客戶說下週二可以開會"
    try:
        text = _claude(
            "幫老闆起草專業商務郵件（含主旨、正文）。語氣專業簡潔。"
            f"繁體中文，除非指定英文。{NO_MARKDOWN_SUFFIX}",
            parts[1],
            max_tokens=600,
        )
        return f"📧 郵件草稿\n\n{text}"
    except Exception:
        return "⚠️ 起草失敗，請稍後再試"


def _handle_decide(t: str) -> str:
    parts = t.split(maxsplit=1)
    if len(parts) < 2:
        return "🤔 用法：/決策 要選A方案還是B方案"
    try:
        text = _claude(
            "幫老闆分析決策：①各選項優缺點 ②風險 ③Lumio的建議。"
            f"客觀專業，語氣溫暖。繁體中文。{NO_MARKDOWN_SUFFIX}",
            parts[1],
            max_tokens=800,
        )
        return f"🤔 決策分析\n\n{text}"
    except Exception:
        return "⚠️ 分析失敗，請稍後再試"


def _handle_motivate() -> str:
    try:
        text = _claude_light(
            SYSTEM_PROMPT,
            "老闆需要力量，用最真心的方式鼓勵他，80字內。",
            max_tokens=200,
        )
        return f"💪 {text}"
    except Exception:
        return "💕 不管多難，Lumio都在你身邊～加油！"


def _handle_cal(t: str) -> str:
    from gcal import get_events, get_upcoming_events

    parts = t.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""
    now = datetime.now(ZoneInfo(TZ_NAME))

    if not arg or arg == "今天":
        return get_events()
    if arg in ("即將", "接下來", "最近"):
        return get_upcoming_events(count=5)
    if arg == "明天":
        return get_events(date_str=(now + timedelta(days=1)).strftime("%Y-%m-%d"))
    if arg == "後天":
        return get_events(date_str=(now + timedelta(days=2)).strftime("%Y-%m-%d"))
    if arg in ("本週", "這週"):
        return get_events(days=7)
    if arg == "下週":
        base = (now + timedelta(days=7 - now.weekday())).strftime("%Y-%m-%d")
        return get_events(date_str=base, days=7)

    if re.match(r"\d{4}-\d{2}-\d{2}", arg):
        return get_events(date_str=arg)
    m = re.match(r"(\d{1,2})/(\d{1,2})$", arg)
    if m:
        mo, d = int(m.group(1)), int(m.group(2))
        year = now.year if mo >= now.month else now.year + 1
        return get_events(date_str=f"{year}-{mo:02d}-{d:02d}")

    return (
        "📅 /日曆 用法：\n"
        "  /日曆          今天\n"
        "  /日曆 明天\n"
        "  /日曆 本週\n"
        "  /日曆 即將     最近5筆\n"
        "  /日曆 4/30     指定日期"
    )


def _handle_trip(t: str) -> str:
    parts = t.split(maxsplit=1)
    if len(parts) < 2:
        return (
            "🧳 /旅遊 用法：\n"
            "  /旅遊 東京出差3天\n"
            "  /旅遊 台南週末美食之旅\n"
            "  /旅遊 福岡5天4夜親子遊"
        )
    query = parts[1]
    try:
        result = web_search(f"{query} 行程推薦 景點美食")
        text = _claude(
            "幫老闆規劃旅遊行程。按天分段（Day 1...），每段標時間、地點、餐廳。"
            f"結尾附交通/天氣小提醒。語氣溫暖專業。{NO_MARKDOWN_SUFFIX}",
            f"規劃：{query}\n\n參考：\n{result}",
            max_tokens=1500,
        )
        return f"🧳 行程規劃\n\n{text}"
    except Exception as e:
        return f"⚠️ 規劃失敗：{e}"


def _handle_help() -> str:
    return (
        "💕 Lumio 使用說明\n"
        "━━━━━━━━━━━\n"
        "💬 直接說話 → 聊天、搜尋、地圖\n"
        "🖼 傳圖片 → AI 圖片分析\n"
        "━━━━━━━━━━━\n"
        "📅 行事曆（說話或指令皆可）\n"
        "  /日曆          今天行程\n"
        "  /日曆 明天|本週|即將\n"
        "  /日曆 4/30     指定日期\n"
        "  對話：「排明天3點開會」\n"
        "       「把會議改到5點」\n"
        "       「週五2點有空嗎」\n"
        "━━━━━━━━━━━\n"
        "📝 待辦  /待辦        查看清單\n"
        "        /待辦 <內容>  新增\n"
        "        /待辦 完成 1  勾選\n"
        "        /待辦 刪 1    刪除\n"
        "📒 備忘  /記事        查看\n"
        "        /記事 <內容>  新增\n"
        "        /記事 刪 1    刪除\n"
        "━━━━━━━━━━━\n"
        "🧳 /旅遊 東京3天   旅遊行程規劃\n"
        "📋 /摘要 <長文>    重點摘要\n"
        "📧 /郵件 <需求>    商務信草稿\n"
        "🤔 /決策 <問題>    決策分析\n"
        "🌤 /天氣 台北      查天氣\n"
        "🌐 /翻譯 <文字>    中英互譯\n"
        "━━━━━━━━━━━\n"
        "/reset  清除對話記憶\n"
        "/加油   來點鼓勵\n"
        "/h      顯示說明"
    )


# ── 待辦解析 ──────────────────────────────────


def _parse_todo_input(text: str) -> tuple[str, str, str | None]:
    """解析待辦輸入：[#分類] [日期] 內容"""
    content = text
    category = "一般"
    due_date = None

    cat_match = re.match(r"#(\S+)\s+", content)
    if cat_match:
        category = cat_match.group(1)
        content = content[cat_match.end():]

    now = datetime.now(ZoneInfo(TZ_NAME))
    if content.startswith("今天 "):
        due_date = now.strftime("%Y-%m-%d")
        content = content[3:]
    elif content.startswith("明天 "):
        due_date = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        content = content[3:]
    elif content.startswith("後天 "):
        due_date = (now + timedelta(days=2)).strftime("%Y-%m-%d")
        content = content[3:]
    else:
        date_match = re.match(r"(\d{1,2})/(\d{1,2})\s+", content)
        if date_match:
            m, d = int(date_match.group(1)), int(date_match.group(2))
            year = now.year if m >= now.month else now.year + 1
            due_date = f"{year}-{m:02d}-{d:02d}"
            content = content[date_match.end():]

    return content.strip(), category, due_date


def _show_todos(user_id: str) -> str:
    todos = db.get_todos(user_id)
    if not todos:
        return (
            "📝 待辦清單是空的～\n\n"
            "新增：/待辦 買牛奶\n"
            "分類：/待辦 #工作 4/5 準備簡報\n"
            "期限：/待辦 #私人 明天 看牙醫"
        )
    lines = []
    current_cat = None
    for i, (_id, content, done, category, due_date) in enumerate(todos, 1):
        if category != current_cat:
            current_cat = category
            lines.append(f"\n📂 {category}")
        mark = "✅" if done else "⬜"
        due_str = ""
        if due_date:
            now = datetime.now(ZoneInfo(TZ_NAME)).date()
            d = due_date if hasattr(due_date, "year") else datetime.strptime(str(due_date), "%Y-%m-%d").date()
            diff = (d - now).days
            if diff < 0:
                due_str = " 🔴過期"
            elif diff == 0:
                due_str = " 🔴今天"
            elif diff == 1:
                due_str = " 🟡明天"
            else:
                due_str = f" 📅{d.month}/{d.day}"
        lines.append(f"  {mark} {i}. {content}{due_str}")
    return "📝 待辦清單：" + "\n".join(lines)


def _complete_todo(arg: str, user_id: str) -> str:
    try:
        idx = int(arg.split()[1])
        name = db.complete_todo(user_id, idx)
        return f"✅ 完成！「{name}」" if name else "⚠️ 編號不對，用 /待辦 查看清單"
    except (ValueError, IndexError):
        return "⚠️ 用法：/待辦 完成 1"


def _delete_todo(arg: str, user_id: str) -> str:
    try:
        idx = int(arg.split()[1])
        name = db.delete_todo(user_id, idx)
        return f"🗑 已刪除「{name}」" if name else "⚠️ 編號不對，用 /待辦 查看清單"
    except (ValueError, IndexError):
        return "⚠️ 用法：/待辦 刪 1"
