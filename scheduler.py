"""排程任務：晨報、定時推播、到期提醒"""
from datetime import datetime
from zoneinfo import ZoneInfo

from linebot.v3.messaging import (
    ApiClient, MessagingApi, PushMessageRequest, TextMessage,
)

import db
from config import (
    anthropic_client, line_config, CLAUDE_MODEL,
    TZ_NAME, WEEKDAY_NAMES, GROUP_ID,
)
from prompts import SYSTEM_PROMPT
from services import get_weather
from gcal import get_today_events
from calendar_tw import get_day_context


# ─── 定時推播設定 ───

SCHEDULED_MESSAGES = {
    "noon": {
        "hour": 12, "minute": 0,
        "emoji": "🍱",
        "prompt": (
            "今天是{today}（{weekday}）。現在中午12點了。你是老闆的貼心秘書 Lumio。"
            "{day_context}"
            "老闆忙起來常常忘記吃飯，請溫柔地提醒他。"
            "內容包含：1) 關心他有沒有吃飯 2) 一個簡短的健康或飲食小叮嚀。"
            "語氣像是真的擔心他不吃飯的那種關心。控制在80字內，直接說不要加開場白"
        ),
    },
    "afternoon": {
        "hour": 16, "minute": 0,
        "emoji": "☕",
        "prompt": (
            "今天是{today}（{weekday}）。現在下午4點了。你是老闆的貼心秘書 Lumio。"
            "{day_context}"
            "請給老闆一點能量和溫暖。"
            "內容包含：1) 關心他下午累不累 2) 提醒喝水或稍微休息一下。"
            "語氣像是心疼他太拼，幫他打打氣。控制在80字內，直接說不要加開場白"
        ),
    },
    "night": {
        "hour": 23, "minute": 0,
        "emoji": "🌙",
        "prompt": (
            "今天是{today}（{weekday}）。現在晚上11點了。你是老闆的貼心秘書 Lumio。"
            "{day_context}"
            "請溫柔地提醒老闆該休息了。"
            "內容包含：1) 肯定他今天的辛苦和付出 2) 溫柔催他放下手機早點睡。"
            "語氣要像哄他入睡一樣溫柔。控制在80字內，直接說不要加開場白"
        ),
    },
}


def _push_text(text: str):
    """推播文字訊息到群組"""
    with ApiClient(line_config) as api_client:
        MessagingApi(api_client).push_message(
            PushMessageRequest(to=GROUP_ID, messages=[TextMessage(text=text)])
        )


async def send_morning_briefing():
    """早安晨報：行程 + 天氣 + 待辦 + 節日 + 問候"""
    if not GROUP_ID:
        return
    try:
        now = datetime.now(ZoneInfo(TZ_NAME))
        today = now.strftime("%m月%d日")
        weekday = WEEKDAY_NAMES[now.weekday()]

        calendar_events = get_today_events()
        weather = get_weather("Taipei")
        if weather:
            weather = f"🌤 台北天氣：{weather}"

        due_todos = db.get_due_todos()
        todo_text = ""
        if due_todos:
            lines = []
            for uid, content, due in due_todos:
                tag = "⚠️ 今天到期" if str(due) == str(now.date()) else "📌 明天到期"
                lines.append(f"  {tag} {content}")
            todo_text = "📝 待辦提醒：\n" + "\n".join(lines)

        day_context = get_day_context(now)
        briefing_data = "\n\n".join(filter(None, [calendar_events, weather, todo_text]))

        prompt = (
            f"今天是{today}（{weekday}）早上8點。{day_context}\n"
            f"以下是今天的資訊：\n{briefing_data}\n\n"
            "你是老闆的貼心秘書 Lumio，請幫老闆整理一份簡潔的早安晨報。"
            "格式：先溫暖問候一句，然後列出今日重點（行程、天氣、待辦提醒）。"
            "如果沒有行程就不用提行程，沒有待辦就不用提待辦。"
            "最後加一句正能量鼓勵。控制在 200 字內，不要使用 Markdown。"
        )
        resp = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        _push_text(f"☀️ {resp.content[0].text}")
    except Exception as e:
        print(f"[晨報推播錯誤] {e}")


async def send_scheduled_message(slot: str):
    """發送定時推播訊息（午餐/下午/晚安）"""
    if not GROUP_ID:
        return
    config = SCHEDULED_MESSAGES[slot]
    try:
        now = datetime.now(ZoneInfo(TZ_NAME))
        today = now.strftime("%m月%d日")
        weekday = WEEKDAY_NAMES[now.weekday()]
        day_context = get_day_context(now)
        prompt = config["prompt"].format(today=today, weekday=weekday, day_context=day_context)
        resp = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        _push_text(f"{config['emoji']} {resp.content[0].text}")
    except Exception as e:
        print(f"[定時推播錯誤][{slot}] {e}")


async def check_due_reminders():
    """檢查待辦到期提醒（每天 09:00 和 20:00 執行）"""
    if not GROUP_ID:
        return
    try:
        due_todos = db.get_due_todos()
        if not due_todos:
            return
        now = datetime.now(ZoneInfo(TZ_NAME))
        lines = []
        for uid, content, due in due_todos:
            tag = "🔴 今天到期" if str(due) == str(now.date()) else "🟡 明天到期"
            lines.append(f"{tag} {content}")
        msg = "📝 待辦到期提醒！\n\n" + "\n".join(lines) + "\n\n記得處理喔～ 💪"
        _push_text(msg)
    except Exception as e:
        print(f"[待辦提醒錯誤] {e}")
