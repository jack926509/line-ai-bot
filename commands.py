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

    if t.startswith("/行程") or t.startswith("/trip"):
        return _handle_trip(text)

    if t.startswith("/search") or t.startswith("/搜尋"):
        return _handle_search(t)

    if t.startswith("/weather") or t.startswith("/天氣"):
        return _handle_weather(t)

    if t.startswith("/translate") or t.startswith("/翻譯"):
        return _handle_translate(t)

    if t.startswith("/摘要") or t.startswith("/summary"):
        return _handle_summary(t)

    if t.startswith("/郵件") or t.startswith("/email"):
        return _handle_email(t)

    if t.startswith("/決策") or t.startswith("/decide"):
        return _handle_decide(t)

    if t in ("/motivate", "/加油", "/鼓勵"):
        return _handle_motivate()

    if t in ("/help", "/幫助", "/h"):
        return _handle_help()

    return None


# ── 個別指令實作 ──────────────────────────────


def handle_reset_memory(user_id: str) -> str:
    db.clear_history(user_id)
    return "🔄 對話記憶已清除～\nLumio 會重新認識你，但待辦事項不會受影響喔！"


def handle_todo(text: str, user_id: str) -> str:
    t = text.strip()
    parts = t.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        return _show_todos(user_id)

    if arg.startswith("完成 ") or arg.startswith("done "):
        return _complete_todo(arg, user_id)

    if arg.startswith("刪除 ") or arg.startswith("del "):
        return _delete_todo(arg, user_id)

    if arg in ("清空", "clear"):
        db.clear_todos(user_id)
        return "🗑 待辦清單已清空～"

    content, category, due_date = _parse_todo_input(arg)
    count = db.add_todo(user_id, content, category=category, due_date=due_date)
    result = f"📝 已新增待辦：「{content}」"
    if category != "一般":
        result += f"\n📂 分類：{category}"
    if due_date:
        result += f"\n📅 到期：{due_date}"
    result += f"\n目前共 {count} 項待辦事項"
    return result


def handle_note(text: str, user_id: str) -> str:
    t = text.strip()
    parts = t.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        notes = db.get_notes(user_id)
        if not notes:
            return "📒 備忘錄是空的喔～\n用法：/記事 客戶說預算上限500萬"
        lines = ["📒 最近的備忘錄："]
        for i, (_id, content, created_at) in enumerate(notes, 1):
            time_str = created_at.strftime("%m/%d %H:%M") if hasattr(created_at, 'strftime') else str(created_at)[:16]
            lines.append(f"  {i}. {content}\n     🕐 {time_str}")
        return "\n".join(lines)

    if arg.startswith("刪除 ") or arg.startswith("del "):
        try:
            idx = int(arg.split()[1])
            name = db.delete_note(user_id, idx)
            if name:
                return f"🗑 已刪除備忘：「{name}」"
            return "⚠️ 編號不對喔，用 /記事 查看清單"
        except (ValueError, IndexError):
            return "⚠️ 用法：/記事 刪除 1"

    if arg in ("清空", "clear"):
        db.clear_notes(user_id)
        return "🗑 備忘錄已清空～"

    count = db.add_note(user_id, arg)
    return f"📒 已記下：「{arg}」\n目前共 {count} 則備忘"


# ── 內部輔助 ──────────────────────────────────


def _claude(system: str, user_msg: str, max_tokens: int = 500) -> str:
    """共用 Claude 呼叫（Sonnet，用於需要高品質的任務）"""
    resp = anthropic_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return resp.content[0].text


def _claude_light(system: str, user_msg: str, max_tokens: int = 300) -> str:
    """輕量 Claude 呼叫（Haiku，用於簡單任務以節省費用）"""
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
        return "🔍 用法：/搜尋 <關鍵字>\n例如：/搜尋 台積電最新股價"
    query = parts[1]
    try:
        search_result = web_search(query)
        text = _claude(
            "你是大老闆的貼心秘書 Lumio。老闆請你搜尋了一些資料，"
            "請根據搜尋結果，綜合多個來源，用簡潔易懂的方式整理重點回覆老闆。\n"
            "整理原則：\n"
            "1. 先給一句話結論\n"
            "2. 再列出 3~5 個重點，標註資訊來自哪些來源\n"
            "3. 如果不同來源說法不同，簡要提及差異\n"
            "4. 最後附上參考來源連結\n"
            "使用繁體中文，語氣溫暖專業。如果搜尋結果不夠完整就如實說明。"
            f"重要：你在 LINE 上回覆，{NO_MARKDOWN_SUFFIX}",
            f"搜尋「{query}」的結果：\n\n{search_result}\n\n請綜合多來源整理重點回覆。",
            max_tokens=1000,
        )
        return f"🔍 搜尋結果整理～\n\n{text}"
    except Exception as e:
        return f"⚠️ 搜尋失敗：{e}"


def _handle_weather(t: str) -> str:
    from services import get_weather
    parts = t.split()
    city = parts[1] if len(parts) > 1 else "Taipei"
    result = get_weather(city)
    return f"🌤 {result}" if result else "⚠️ 無法取得天氣資訊，請稍後再試"


def _handle_translate(t: str) -> str:
    parts = t.split(maxsplit=1)
    if len(parts) < 2:
        return "🌐 用法：/翻譯 Hello, how are you?\n（自動偵測語言互譯中英文）"
    try:
        text = _claude_light(
            "你是翻譯助手。如果輸入是中文就翻成英文，如果是英文就翻成中文。只回覆翻譯結果，不加解釋。",
            parts[1],
        )
        return f"🌐 翻譯結果：\n{text}"
    except Exception:
        return "⚠️ 翻譯失敗，請稍後再試"


def _handle_summary(t: str) -> str:
    parts = t.split(maxsplit=1)
    if len(parts) < 2:
        return "📋 用法：/摘要 <貼上長文內容>\n幫你快速抓出重點～"
    try:
        text = _claude(
            "你是大老闆的貼心秘書。老闆很忙，請用最精簡的方式摘要以下內容。"
            "格式：1) 一句話總結 2) 3~5 個重點條列 3) 需要老闆注意或決策的事項（如有）。"
            f"使用繁體中文，語氣專業但溫暖。{NO_MARKDOWN_SUFFIX}",
            parts[1],
            max_tokens=800,
        )
        return f"📋 摘要整理好了～\n\n{text}"
    except Exception:
        return "⚠️ 摘要失敗，請稍後再試"


def _handle_email(t: str) -> str:
    parts = t.split(maxsplit=1)
    if len(parts) < 2:
        return "📧 用法：/郵件 <描述需求>\n例如：/郵件 回覆客戶說下週二可以開會"
    try:
        text = _claude(
            "你是大老闆的秘書，幫老闆起草專業的商務郵件。"
            "格式包含：主旨、正文。語氣專業得體、簡潔有力。"
            f"使用繁體中文，除非老闆指定用英文。{NO_MARKDOWN_SUFFIX}",
            parts[1],
            max_tokens=600,
        )
        return f"📧 郵件草稿～\n\n{text}"
    except Exception:
        return "⚠️ 郵件起草失敗，請稍後再試"


def _handle_decide(t: str) -> str:
    parts = t.split(maxsplit=1)
    if len(parts) < 2:
        return "🤔 用法：/決策 <描述問題或選項>\n例如：/決策 該先拓展日本市場還是東南亞市場"
    try:
        text = _claude(
            "你是大老闆的高級策略顧問兼貼心秘書。"
            "幫老闆分析決策，格式：1) 各選項的優缺點 2) 風險評估 3) Lumio的建議。"
            f"分析要客觀專業，但語氣保持溫暖貼心。使用繁體中文。{NO_MARKDOWN_SUFFIX}",
            parts[1],
            max_tokens=800,
        )
        return f"🤔 決策分析～\n\n{text}"
    except Exception:
        return "⚠️ 分析失敗，請稍後再試"


def _handle_motivate() -> str:
    try:
        text = _claude_light(
            SYSTEM_PROMPT,
            "老闆現在需要一點力量，用你最真心的方式鼓勵他，讓他感受到不管多難都有你在。控制在80字內",
            max_tokens=200,
        )
        return f"💪 {text}"
    except Exception:
        return "💕 不管遇到什麼困難，Lumio都在你身邊喔～加油！"


def _handle_cal(t: str) -> str:
    from gcal import get_events, get_upcoming_events
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    parts = t.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    now = datetime.now(ZoneInfo(TZ_NAME))

    if not arg or arg in ("今天", "today"):
        return get_events()

    if arg in ("即將", "upcoming", "接下來", "最近"):
        return get_upcoming_events(count=5)

    if arg in ("明天", "tomorrow"):
        date_str = (now + timedelta(days=1)).strftime("%Y-%m-%d")
        return get_events(date_str=date_str)

    if arg in ("後天",):
        date_str = (now + timedelta(days=2)).strftime("%Y-%m-%d")
        return get_events(date_str=date_str)

    if arg in ("本週", "這週", "week"):
        return get_events(days=7)

    if arg in ("下週", "next week"):
        base_str = (now + timedelta(days=7 - now.weekday())).strftime("%Y-%m-%d")
        return get_events(date_str=base_str, days=7)

    # 支援 YYYY-MM-DD 或 MM/DD
    import re
    if re.match(r"\d{4}-\d{2}-\d{2}", arg):
        return get_events(date_str=arg)
    m = re.match(r"(\d{1,2})/(\d{1,2})", arg)
    if m:
        month, day = int(m.group(1)), int(m.group(2))
        year = now.year if month >= now.month else now.year + 1
        date_str = f"{year}-{month:02d}-{day:02d}"
        return get_events(date_str=date_str)

    return (
        "📅 /日曆 使用方式：\n"
        "  /日曆 → 今天行程\n"
        "  /日曆 明天\n"
        "  /日曆 本週\n"
        "  /日曆 即將 → 最近 5 筆\n"
        "  /日曆 4/30 → 指定日期\n"
        "  /日曆 2025-05-01 → 指定日期"
    )


def _handle_trip(text: str) -> str:
    t = text.strip()
    parts = t.split(maxsplit=1)
    if len(parts) < 2:
        return (
            "🧳 行程規劃助手\n\n"
            "用法：/行程 <描述你的旅行需求>\n\n"
            "範例：\n"
            "  /行程 下週去東京出差3天\n"
            "  /行程 週末台南兩天一夜美食之旅\n"
            "  /行程 福岡5天4夜親子遊"
        )
    query = parts[1]
    try:
        search_result = web_search(f"{query} 行程推薦 景點美食")
        text = _claude(
            "你是大老闆的貼心秘書 Lumio，老闆要你幫忙規劃行程。"
            "請根據搜尋結果，整理出一份完整的行程表。\n"
            "格式要求：\n"
            "1. 按天數分段（Day 1、Day 2...）\n"
            "2. 每個時段標註時間和地點\n"
            "3. 包含景點、餐廳推薦\n"
            "4. 最後附上實用小提醒（交通、天氣、注意事項）\n"
            f"重要：{NO_MARKDOWN_SUFFIX}"
            "語氣溫暖專業，像是真的幫老闆安排好了一切。",
            f"幫我規劃：{query}\n\n參考資訊：\n{search_result}",
            max_tokens=1500,
        )
        return f"🧳 行程規劃好了～\n\n{text}"
    except Exception as e:
        return f"⚠️ 行程規劃失敗：{e}"


def _handle_help() -> str:
    return (
        "💕 Lumio 秘書使用說明\n"
        "━━━━━━━━━━━━━━━\n"
        "💬 聊天：直接跟我說話就好～\n"
        "🔍 搜尋：/搜尋 台積電最新消息\n"
        "📍 地圖：聊天提到地點自動附地圖\n"
        "🧳 行程：/行程 東京出差3天\n"
        "━━━━━━━━━━━━━━━\n"
        "📅 日曆（直接對話）：\n"
        "　　「今天有什麼行程」\n"
        "　　「幫我排明天3點開會」\n"
        "　　「把會議改到下午5點」\n"
        "　　「週五2點有空嗎」\n"
        "　　「取消週五的聚餐」\n"
        "📅 日曆（快捷指令）：\n"
        "　　/日曆 → 今天\n"
        "　　/日曆 明天｜本週｜即將\n"
        "　　/日曆 4/30 → 指定日期\n"
        "━━━━━━━━━━━━━━━\n"
        "📝 待辦：/待辦 買牛奶\n"
        "　　　　/待辦 #工作 4/5 準備簡報\n"
        "　　　　/待辦 #私人 明天 看牙醫\n"
        "　　　　/待辦 完成 1 ｜ /待辦 清空\n"
        "📒 記事：/記事 客戶預算500萬\n"
        "　　　　/記事（查看）｜ /記事 刪除 1\n"
        "━━━━━━━━━━━━━━━\n"
        "📋 摘要：/摘要 <長文內容>\n"
        "📧 郵件：/郵件 回覆客戶...\n"
        "🤔 決策：/決策 A方案還是B方案\n"
        "🌤 天氣：/天氣 台北\n"
        "🌐 翻譯：/翻譯 你好嗎\n"
        "💪 加油：/加油\n"
        "🔄 清除記憶：/清除記憶\n"
        "🖼 圖片：直接傳圖給我～\n"
        "━━━━━━━━━━━━━━━\n"
        "有什麼都可以跟Lumio說喔！"
    )


# ── 待辦解析 ──────────────────────────────────


def _parse_todo_input(text: str) -> tuple[str, str, str | None]:
    """解析待辦輸入：/待辦 [#分類] [日期] 內容"""
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
            "📝 待辦清單是空的喔～\n\n"
            "新增方式：\n"
            "  /待辦 買牛奶\n"
            "  /待辦 #工作 4/5 準備簡報\n"
            "  /待辦 #私人 明天 看牙醫"
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
            d = due_date if hasattr(due_date, 'year') else datetime.strptime(str(due_date), "%Y-%m-%d").date()
            diff = (d - now).days
            if diff < 0:
                due_str = " 🔴已過期"
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
        if name:
            return f"✅ 太棒了！「{name}」完成囉～"
        return "⚠️ 編號不對喔，用 /待辦 查看清單"
    except (ValueError, IndexError):
        return "⚠️ 用法：/待辦 完成 1"


def _delete_todo(arg: str, user_id: str) -> str:
    try:
        idx = int(arg.split()[1])
        name = db.delete_todo(user_id, idx)
        if name:
            return f"🗑 已刪除「{name}」"
        return "⚠️ 編號不對喔，用 /待辦 查看清單"
    except (ValueError, IndexError):
        return "⚠️ 用法：/待辦 刪除 1"
