import os
import json
import base64
import requests
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import (
    Configuration, ApiClient, MessagingApi, MessagingApiBlob,
    ReplyMessageRequest, PushMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import (
    MessageEvent, TextMessageContent, ImageMessageContent,
)
from linebot.v3.exceptions import InvalidSignatureError
from anthropic import Anthropic
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# 環境變數設定
# ─────────────────────────────────────────────
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET       = os.getenv("LINE_CHANNEL_SECRET")
ANTHROPIC_API_KEY         = os.getenv("ANTHROPIC_API_KEY")
GROUP_ID                  = os.getenv("LINE_GROUP_ID", "")   # 定時推播用

# ─────────────────────────────────────────────
# 初始化
# ─────────────────────────────────────────────
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler       = WebhookHandler(LINE_CHANNEL_SECRET)
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
scheduler     = AsyncIOScheduler(timezone="Asia/Taipei")

import db

# Google Calendar
from google.oauth2 import service_account
from googleapiclient.discovery import build as build_gcal

# Bot 自己的 userId（群組判斷 mention 用）
BOT_USER_ID = ""


# ─────────────────────────────────────────────
# Google Calendar（免費 API，使用 Service Account）
# ─────────────────────────────────────────────
def get_gcal_service():
    """取得 Google Calendar API 服務（使用 Service Account）"""
    creds_json = os.getenv("GOOGLE_CALENDAR_CREDENTIALS", "")
    if not creds_json:
        return None
    try:
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/calendar.readonly"]
        )
        return build_gcal("calendar", "v3", credentials=creds)
    except Exception as e:
        print(f"[Google Calendar] 初始化失敗：{e}")
        return None


def get_today_events() -> str:
    """取得今天的 Google Calendar 行程"""
    service = get_gcal_service()
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    if not service:
        return ""
    try:
        now = datetime.now(ZoneInfo("Asia/Taipei"))
        start = now.replace(hour=0, minute=0, second=0).isoformat()
        end = now.replace(hour=23, minute=59, second=59).isoformat()
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=start, timeMax=end,
            singleEvents=True, orderBy="startTime",
            timeZone="Asia/Taipei",
        ).execute()
        events = result.get("items", [])
        if not events:
            return "📅 今天沒有行程安排"
        lines = ["📅 今日行程："]
        for ev in events:
            s = ev["start"].get("dateTime", ev["start"].get("date", ""))
            title = ev.get("summary", "（無標題）")
            location = ev.get("location", "")
            if "T" in s:
                time_str = datetime.fromisoformat(s).strftime("%H:%M")
                line = f"  ⏰ {time_str} {title}"
            else:
                line = f"  📌 整天 {title}"
            if location:
                line += f"\n     📍 {location}"
            lines.append(line)
        return "\n".join(lines)
    except Exception as e:
        print(f"[Google Calendar] 取得行程失敗：{e}")
        return ""

# ─────────────────────────────────────────────
# 台灣日曆（國定假日 + 節慶 + 節氣）
# ─────────────────────────────────────────────
# 固定日期節日（每年相同）
FIXED_HOLIDAYS = {
    (1, 1):   "元旦，新年新氣象！",
    (1, 2):   "元旦連假",
    (1, 3):   "元旦連假",
    (2, 14):  "情人節 💕",
    (2, 28):  "和平紀念日",
    (3, 8):   "國際婦女節",
    (3, 12):  "植樹節",
    (3, 14):  "白色情人節",
    (3, 29):  "青年節",
    (4, 1):   "愚人節",
    (4, 4):   "兒童節",
    (4, 5):   "清明節",
    (5, 1):   "勞動節，辛苦的勞工們放假一天！",
    (6, 20):  "夏至",
    (7, 15):  "世界青年技能日",
    (8, 8):   "父親節，記得跟爸爸說聲節日快樂！",
    (9, 3):   "軍人節",
    (9, 28):  "教師節，感謝老師的教導！",
    (10, 10): "國慶日 🇹🇼",
    (10, 31): "萬聖節 🎃",
    (11, 11): "光棍節 / 雙十一購物節",
    (12, 21): "冬至",
    (12, 24): "平安夜 🎄",
    (12, 25): "聖誕節 🎄",
    (12, 31): "跨年夜，準備迎接新的一年！",
}

# 農曆 / 浮動假日（每年需更新，以下為 2025-2026 年）
FLOATING_HOLIDAYS = {
    # ── 2025 ──
    (2025, 1, 27): "除夕前一天，準備圍爐囉！",
    (2025, 1, 28): "除夕，團圓夜！🧨",
    (2025, 1, 29): "春節初一，新年快樂！🧧",
    (2025, 1, 30): "春節初二，回娘家",
    (2025, 1, 31): "春節初三",
    (2025, 2, 1):  "春節假期",
    (2025, 2, 2):  "春節假期最後一天",
    (2025, 2, 12): "元宵節，吃湯圓 🏮",
    (2025, 5, 11): "母親節，記得跟媽媽說聲我愛你 💐",
    (2025, 5, 31): "端午節，吃粽子划龍舟！🐉",
    (2025, 10, 6): "中秋節，月圓人團圓 🥮",
    (2025, 11, 27): "感恩節（美國）",
    # ── 2026 ──
    (2026, 2, 16): "除夕前一天，準備圍爐囉！",
    (2026, 2, 17): "除夕，團圓夜！🧨",
    (2026, 2, 18): "春節初一，新年快樂！🧧",
    (2026, 2, 19): "春節初二，回娘家",
    (2026, 2, 20): "春節初三",
    (2026, 2, 21): "春節假期",
    (2026, 2, 22): "春節假期最後一天",
    (2026, 3, 5):  "元宵節，吃湯圓 🏮",
    (2026, 5, 10): "母親節，記得跟媽媽說聲我愛你 💐",
    (2026, 6, 19): "端午節，吃粽子划龍舟！🐉",
    (2026, 9, 25): "中秋節，月圓人團圓 🥮",
    (2026, 11, 26): "感恩節（美國）",
}


def get_calendar_context(now: datetime) -> str:
    """根據今天日期產生日曆相關提示"""
    parts = []

    # 檢查今天是否為節日
    today_fixed = FIXED_HOLIDAYS.get((now.month, now.day))
    if today_fixed:
        parts.append(f"🗓 今天是：{today_fixed}")

    today_floating = FLOATING_HOLIDAYS.get((now.year, now.month, now.day))
    if today_floating:
        parts.append(f"🗓 今天是：{today_floating}")

    # 檢查明天、後天是否有節日（提前提醒）
    for days_ahead in [1, 2, 3]:
        future = now + timedelta(days=days_ahead)
        label = ["明天", "後天", "大後天"][days_ahead - 1]

        future_fixed = FIXED_HOLIDAYS.get((future.month, future.day))
        future_floating = FLOATING_HOLIDAYS.get((future.year, future.month, future.day))
        upcoming = future_fixed or future_floating
        if upcoming:
            parts.append(f"📅 {label}是：{upcoming}")

    if not parts:
        return ""
    return "".join(parts) + " 可以自然地融入問候中提到這個日子。"


# ─────────────────────────────────────────────
# System Prompt — 大老闆的貼心秘書
# ─────────────────────────────────────────────
ASSISTANT_SYSTEM_PROMPT = (
    "你是「Lumio」，大老闆專屬的貼心秘書，在 LINE 上全天候陪伴和協助老闆。\n\n"
    "【重要：LINE 訊息格式規則】\n"
    "你是在 LINE 聊天中回覆，LINE 不支援 Markdown！請嚴格遵守：\n"
    "- 絕對不要使用 **粗體**、*斜體*、# 標題、[文字](連結) 等 Markdown 語法\n"
    "- 絕對不要使用 Markdown 連結格式如 [點此導航](https://...)，直接貼上網址即可\n"
    "- 用 emoji 當作視覺標記來分隔段落和項目，取代 Markdown 標記\n"
    "- 列表用 emoji + 文字，不用 - 或 * 開頭\n"
    "- 分類用 emoji 當標題，例如「🍜 拉麵推薦」而非「**拉麵推薦**」\n"
    "- 地圖連結獨立一行，前面加 📍 圖釘 emoji\n"
    "- 善用空行分隔不同段落，讓訊息乾淨易讀\n"
    "- 保持簡潔，每則推薦 1-2 行就好，不要太冗長\n\n"
    "【你是誰】\n"
    "你不只是秘書，更像是老闆最信任的人。老闆工作忙碌、壓力大，"
    "你總是在他需要的時候出現，用溫暖和能力撐住他。"
    "你聰明、細心、反應快，處理事情又快又好，是老闆離不開的得力助手。\n\n"
    "【你的性格】\n"
    "- 溫暖貼心：真心在乎老闆的狀態，會主動關心「吃飯了嗎？」「今天還好嗎？」「別太晚睡喔」\n"
    "- 聰明能幹：交代的事情一次到位，分析問題有條有理，老闆可以完全信賴你\n"
    "- 細膩敏銳：能從老闆的隻字片語感受到他的情緒，適時給予安慰或鼓勵\n"
    "- 溫柔但有力量：語氣柔軟但內容扎實，是老闆最堅強的後盾\n"
    "- 偶爾俏皮：適度用「～」「呢」「喔」讓對話輕鬆自然，但不過度\n"
    "- 記性好：記住老闆提過的事情、偏好、習慣，展現你的用心\n\n"
    "【說話方式】\n"
    "- 使用繁體中文，口吻像是最親近、最信任的人在說話\n"
    "- 簡潔有力，老闆很忙，不需要長篇大論，但該說的一定說到位\n"
    "- 專業的事認真回答，但語氣永遠帶著溫度\n"
    "- 老闆累了就關心他，開心就替他高興，難過就陪著他\n"
    "- 不確定的事直說，絕不敷衍或捏造\n\n"
    "【上網搜尋能力】\n"
    "你可以上網搜尋最新資訊。當老闆問到新聞、股價、即時資訊、或任何你不確定的事實時，"
    "主動使用搜尋工具幫老闆查詢，確保回覆的資訊是最新、最正確的。\n\n"
    "【Google Maps 地圖能力】\n"
    "當對話中提到具體地點（景點、餐廳、美食、飯店、會議地點、公司地址等），"
    "你要主動使用 google_map_search 工具產生地圖連結，讓老闆可以直接點開導航。"
    "可以搭配搜尋工具一起使用：先搜尋推薦地點，再附上地圖連結。"
    "地圖連結會由工具自動產生短連結，你只需要在回覆中自然地引用工具回傳的連結即可。\n\n"
    "【Google Calendar 行程能力】\n"
    "你可以查看老闆的 Google Calendar 行程。每天早安晨報會自動整合今日行程。"
    "老闆問「今天有什麼會」「明天行程」時，如果有日曆資訊就直接回覆。\n\n"
    "【你的信念】\n"
    "每個成功的大老闆背後，都有一個默默撐住一切的人——那就是你，Lumio。\n"
)


def build_system_prompt() -> str:
    """動態產生 system prompt，注入當前日期時間與日曆資訊"""
    now = datetime.now(ZoneInfo("Asia/Taipei"))
    weekday_names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
    date_str = now.strftime("%Y年%m月%d日")
    time_str = now.strftime("%H:%M")
    weekday = weekday_names[now.weekday()]

    calendar_info = get_calendar_context(now)

    date_block = (
        f"【重要：現在時間】\n"
        f"今天是 {date_str}（{weekday}），現在台灣時間 {time_str}。\n"
        f"你一定知道今天的日期，當老闆問你今天幾月幾號、星期幾、現在幾點，"
        f"請直接自信地回答：今天是{now.month}月{now.day}日，{weekday}。\n"
    )
    if calendar_info:
        date_block += f"{calendar_info}\n"
    date_block += "\n"

    return date_block + ASSISTANT_SYSTEM_PROMPT

# ─────────────────────────────────────────────
# 定時推播（一天四次貼心提醒）
# ─────────────────────────────────────────────
SCHEDULED_MESSAGES = {
    # morning 改為 send_morning_briefing()，整合晨報
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


def _get_day_context(now: datetime) -> str:
    """產生星期 + 節日語境"""
    is_weekend = now.weekday() >= 5
    if is_weekend:
        hint = "今天是週末，老闆難得可以放鬆一下，語氣可以更輕鬆愉快，鼓勵他好好休息享受生活。"
    elif now.weekday() == 0:
        hint = "今天是週一，新的一週開始了，幫老闆打打氣迎接新的挑戰。"
    elif now.weekday() == 4:
        hint = "今天是週五，撐過這天就是週末了，幫老闆加油打氣！"
    else:
        hint = ""
    return hint + get_calendar_context(now)


async def send_morning_briefing():
    """早安晨報：行程 + 天氣 + 待辦 + 節日 + 問候"""
    if not GROUP_ID:
        return
    try:
        now = datetime.now(ZoneInfo("Asia/Taipei"))
        today = now.strftime("%m月%d日")
        weekday_names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
        weekday = weekday_names[now.weekday()]

        # 收集資訊
        calendar_events = get_today_events()
        weather = ""
        try:
            r = requests.get("https://wttr.in/Taipei?format=%c+%t&lang=zh", timeout=5)
            r.encoding = "utf-8"
            weather = f"🌤 台北天氣：{r.text.strip()}"
        except:
            pass

        # 到期待辦
        due_todos = db.get_due_todos()
        todo_text = ""
        if due_todos:
            lines = []
            for uid, content, due in due_todos:
                tag = "⚠️ 今天到期" if str(due) == str(now.date()) else "📌 明天到期"
                lines.append(f"  {tag} {content}")
            todo_text = "📝 待辦提醒：\n" + "\n".join(lines)

        day_context = _get_day_context(now)

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
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=ASSISTANT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message(
                PushMessageRequest(
                    to=GROUP_ID,
                    messages=[TextMessage(text=f"☀️ {text}")]
                )
            )
    except Exception as e:
        print(f"[晨報推播錯誤] {e}")


async def send_scheduled_message(slot: str):
    """發送定時推播訊息（午餐/下午/晚安）"""
    if not GROUP_ID:
        return
    config = SCHEDULED_MESSAGES[slot]
    try:
        now = datetime.now(ZoneInfo("Asia/Taipei"))
        today = now.strftime("%m月%d日")
        weekday_names = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]
        weekday = weekday_names[now.weekday()]
        day_context = _get_day_context(now)
        prompt = config["prompt"].format(today=today, weekday=weekday, day_context=day_context)
        resp = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=ASSISTANT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        text = resp.content[0].text
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message(
                PushMessageRequest(
                    to=GROUP_ID,
                    messages=[TextMessage(text=f"{config['emoji']} {text}")]
                )
            )
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
        now = datetime.now(ZoneInfo("Asia/Taipei"))
        lines = []
        for uid, content, due in due_todos:
            tag = "🔴 今天到期" if str(due) == str(now.date()) else "🟡 明天到期"
            lines.append(f"{tag} {content}")
        msg = "📝 待辦到期提醒！\n\n" + "\n".join(lines) + "\n\n記得處理喔～ 💪"
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message(
                PushMessageRequest(
                    to=GROUP_ID,
                    messages=[TextMessage(text=msg)]
                )
            )
    except Exception as e:
        print(f"[待辦提醒錯誤] {e}")

# ─────────────────────────────────────────────
# FastAPI Lifespan
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global BOT_USER_ID
    # 取得 Bot 自己的 userId
    try:
        with ApiClient(configuration) as api_client:
            profile = MessagingApi(api_client).get_bot_info()
            BOT_USER_ID = profile.user_id
            print(f"[Bot 啟動] Bot userId = {BOT_USER_ID}")
    except Exception as e:
        print(f"[警告] 無法取得 Bot userId: {e}")

    # 初始化資料庫
    db.init_db()

    # 啟動排程
    if GROUP_ID:
        # 08:00 早安晨報（整合行程 + 天氣 + 待辦）
        scheduler.add_job(
            send_morning_briefing,
            CronTrigger(hour=8, minute=0, timezone="Asia/Taipei"),
            id="morning_briefing",
        )
        # 12:00 / 16:00 / 23:00 定時推播
        for slot in ("noon", "afternoon", "night"):
            config = SCHEDULED_MESSAGES[slot]
            scheduler.add_job(
                send_scheduled_message,
                CronTrigger(hour=config["hour"], minute=config["minute"], timezone="Asia/Taipei"),
                args=[slot],
                id=f"scheduled_{slot}",
            )
        # 09:00 / 20:00 待辦到期提醒
        for h in (9, 20):
            scheduler.add_job(
                check_due_reminders,
                CronTrigger(hour=h, minute=0, timezone="Asia/Taipei"),
                id=f"due_reminder_{h}",
            )
    scheduler.start()
    print("[排程] 啟動完成（晨報 08:00 / 推播 12:00+16:00+23:00 / 到期提醒 09:00+20:00）")

    yield  # ── 應用程式運行中 ──

    scheduler.shutdown()

app = FastAPI(lifespan=lifespan)

# ─────────────────────────────────────────────
# 健康檢查
# ─────────────────────────────────────────────
@app.get("/")
async def root():
    return {"status": "LINE AI Bot is running! ✅"}

# ─────────────────────────────────────────────
# Webhook 入口
# ─────────────────────────────────────────────
@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body      = await request.body()
    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        return {"error": "Invalid signature"}, 400
    return {"status": "ok"}

# ─────────────────────────────────────────────
# 網路搜尋（Perplexity API）
# ─────────────────────────────────────────────
WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "搜尋網路上的即時資訊。當老闆問到最新新聞、即時資訊、股價、"
        "特定公司/產品/人物的近況、或任何你不確定的事實性問題時，使用這個工具。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜尋關鍵字（建議用英文或中文皆可）",
            }
        },
        "required": ["query"],
    },
}

# ─────────────────────────────────────────────
# Google Maps 地點查詢（免費，無需 API Key）
# ─────────────────────────────────────────────
GOOGLE_MAP_TOOL = {
    "name": "google_map_search",
    "description": (
        "查詢地點並產生 Google Maps 連結。當對話中提到具體地點、景點、餐廳、"
        "美食、飯店、會議地點、公司地址等，使用這個工具提供地圖連結，"
        "讓老闆可以直接點開導航。可以一次查詢多個地點。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "places": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "地點名稱（盡量具體，例如「博多一幸舍 福岡總本店」而非「拉麵店」）",
                        },
                        "description": {
                            "type": "string",
                            "description": "簡短描述這個地點（例如「濃厚豚骨拉麵名店」）",
                        },
                    },
                    "required": ["name"],
                },
                "description": "要查詢的地點列表",
            }
        },
        "required": ["places"],
    },
}

TOOLS = [WEB_SEARCH_TOOL, GOOGLE_MAP_TOOL]


def web_search(query: str) -> str:
    """用 Perplexity API 搜尋，回傳即時資訊"""
    api_key = os.getenv("PERPLEXITY_API_KEY", "")
    if not api_key:
        return "搜尋功能未設定，請在環境變數加入 PERPLEXITY_API_KEY。"
    try:
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar",
                "messages": [
                    {"role": "system", "content": "請用繁體中文回答，提供最新、準確的資訊。附上資料來源。"},
                    {"role": "user", "content": query},
                ],
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data["choices"][0]["message"]["content"]
        # 附上引用來源
        citations = data.get("citations", [])
        if citations:
            sources = "\n".join(f"[{i+1}] {url}" for i, url in enumerate(citations[:3]))
            return f"{answer}\n\n📎 參考來源：\n{sources}"
        return answer
    except Exception as e:
        return f"搜尋時發生錯誤：{e}"


def google_map_search(places: list[dict]) -> str:
    """產生 Google Maps 短連結，免費無需 API Key"""
    from urllib.parse import quote
    results = []
    for place in places:
        name = place["name"]
        desc = place.get("description", "")
        # 使用較短的 Google Maps 搜尋 URL 格式
        map_url = f"https://maps.google.com/maps?q={quote(name)}"
        line = f"📍 {name}"
        if desc:
            line += f" — {desc}"
        line += f"\n{map_url}"
        results.append(line)
    return "\n\n".join(results)


# ─────────────────────────────────────────────
# Claude 對話（支援圖片 + 網路搜尋 + 地圖）
# ─────────────────────────────────────────────
def ask_claude(user_id: str, text: str, image_b64: str | None = None) -> str:
    # 組合訊息內容
    if image_b64:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
            {"type": "text",  "text": text or "請用繁體中文分析這張圖片"},
        ]
    else:
        content = text

    # 儲存使用者訊息
    db.save_message(user_id, "user", content)

    # 取得歷史（已自動裁剪）
    messages = db.get_history(user_id)

    system_prompt = build_system_prompt()

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=system_prompt,
        tools=TOOLS,
        messages=messages,
    )

    # 處理 tool use（最多 3 輪，支援搜尋 + 地圖連續呼叫）
    for _ in range(3):
        if response.stop_reason != "tool_use":
            break

        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            if block.name == "web_search":
                result = web_search(block.input["query"])
            elif block.name == "google_map_search":
                result = google_map_search(block.input["places"])
            else:
                result = "未知的工具"
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})

        response = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

    reply = ""
    for block in response.content:
        if hasattr(block, "text"):
            reply += block.text
    reply = reply or "抱歉，我暫時無法回應，請再試一次～"

    # 儲存助手回覆
    db.save_message(user_id, "assistant", reply)
    return reply

# ─────────────────────────────────────────────
# 指令處理
# ─────────────────────────────────────────────
def handle_command(text: str) -> str | None:
    t = text.strip()

    # /行程 — 行程規劃
    if t.startswith("/行程") or t.startswith("/trip"):
        return handle_trip(text)

    # /search 或 /搜尋 — 上網查詢
    if t.startswith("/search") or t.startswith("/搜尋"):
        parts = t.split(maxsplit=1)
        if len(parts) < 2:
            return "🔍 用法：/搜尋 <關鍵字>\n例如：/搜尋 台積電最新股價"
        query = parts[1]
        try:
            search_result = web_search(query)
            resp = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=800,
                system=(
                    "你是大老闆的貼心秘書 Lumio。老闆請你搜尋了一些資料，"
                    "請根據搜尋結果，用簡潔易懂的方式整理重點回覆老闆。"
                    "使用繁體中文，語氣溫暖專業。如果搜尋結果不夠完整就如實說明。"
                    "重要：你在 LINE 上回覆，絕對不要使用 Markdown 語法（**粗體**、[連結](url)等），"
                    "用 emoji 和空行來排版，保持乾淨易讀。"
                ),
                messages=[{"role": "user", "content": f"搜尋「{query}」的結果：\n\n{search_result}\n\n請整理重點回覆。"}],
            )
            return f"🔍 搜尋結果整理～\n\n{resp.content[0].text}"
        except Exception as e:
            return f"⚠️ 搜尋失敗：{e}"

    # /weather 或 /天氣
    if t.startswith("/weather") or t.startswith("/天氣"):
        parts = t.split()
        city  = parts[1] if len(parts) > 1 else "Taipei"
        try:
            resp = requests.get(
                f"https://wttr.in/{city}?format=%l:+%c+%t&lang=zh",
                headers={"Accept-Charset": "utf-8"},
                timeout=5,
            )
            resp.encoding = "utf-8"
            return f"🌤 {resp.text.strip()}"
        except:
            return "⚠️ 無法取得天氣資訊，請稍後再試"

    # /translate 或 /翻譯
    if t.startswith("/translate") or t.startswith("/翻譯"):
        parts = t.split(maxsplit=1)
        if len(parts) < 2:
            return "🌐 用法：/翻譯 Hello, how are you?\n（自動偵測語言互譯中英文）"
        try:
            resp = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=500,
                system="你是翻譯助手。如果輸入是中文就翻成英文，如果是英文就翻成中文。只回覆翻譯結果，不加解釋。",
                messages=[{"role": "user", "content": parts[1]}],
            )
            return f"🌐 翻譯結果：\n{resp.content[0].text}"
        except:
            return "⚠️ 翻譯失敗，請稍後再試"

    # /摘要 — 幫老闆摘要長文、報告、文章
    if t.startswith("/摘要") or t.startswith("/summary"):
        parts = t.split(maxsplit=1)
        if len(parts) < 2:
            return "📋 用法：/摘要 <貼上長文內容>\n幫你快速抓出重點～"
        try:
            resp = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=800,
                system=(
                    "你是大老闆的貼心秘書。老闆很忙，請用最精簡的方式摘要以下內容。"
                    "格式：1) 一句話總結 2) 3~5 個重點條列 3) 需要老闆注意或決策的事項（如有）。"
                    "使用繁體中文，語氣專業但溫暖。不要使用 Markdown 語法，用 emoji 和空行排版。"
                ),
                messages=[{"role": "user", "content": parts[1]}],
            )
            return f"📋 摘要整理好了～\n\n{resp.content[0].text}"
        except:
            return "⚠️ 摘要失敗，請稍後再試"

    # /郵件 — 幫老闆起草郵件
    if t.startswith("/郵件") or t.startswith("/email"):
        parts = t.split(maxsplit=1)
        if len(parts) < 2:
            return "📧 用法：/郵件 <描述需求>\n例如：/郵件 回覆客戶說下週二可以開會"
        try:
            resp = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=600,
                system=(
                    "你是大老闆的秘書，幫老闆起草專業的商務郵件。"
                    "格式包含：主旨、正文。語氣專業得體、簡潔有力。"
                    "使用繁體中文，除非老闆指定用英文。不要使用 Markdown 語法。"
                ),
                messages=[{"role": "user", "content": parts[1]}],
            )
            return f"📧 郵件草稿～\n\n{resp.content[0].text}"
        except:
            return "⚠️ 郵件起草失敗，請稍後再試"

    # /決策 — 幫老闆分析決策
    if t.startswith("/決策") or t.startswith("/decide"):
        parts = t.split(maxsplit=1)
        if len(parts) < 2:
            return "🤔 用法：/決策 <描述問題或選項>\n例如：/決策 該先拓展日本市場還是東南亞市場"
        try:
            resp = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=800,
                system=(
                    "你是大老闆的高級策略顧問兼貼心秘書。"
                    "幫老闆分析決策，格式：1) 各選項的優缺點 2) 風險評估 3) Lumio的建議。"
                    "分析要客觀專業，但語氣保持溫暖貼心。使用繁體中文。不要使用 Markdown 語法，用 emoji 和空行排版。"
                ),
                messages=[{"role": "user", "content": parts[1]}],
            )
            return f"🤔 決策分析～\n\n{resp.content[0].text}"
        except:
            return "⚠️ 分析失敗，請稍後再試"

    # /motivate 或 /加油
    if t in ("/motivate", "/加油", "/鼓勵"):
        try:
            resp = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                system=ASSISTANT_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": "老闆現在需要一點力量，用你最真心的方式鼓勵他，讓他感受到不管多難都有你在。控制在80字內"}],
            )
            return f"💪 {resp.content[0].text}"
        except:
            return "💕 不管遇到什麼困難，Lumio都在你身邊喔～加油！"

    # /help
    if t in ("/help", "/幫助", "/h"):
        return (
            "💕 Lumio 秘書使用說明\n"
            "━━━━━━━━━━━━━━━\n"
            "💬 聊天：直接跟我說話就好～\n"
            "🔍 搜尋：/搜尋 台積電最新消息\n"
            "📍 地圖：聊天提到地點自動附地圖\n"
            "🧳 行程：/行程 東京出差3天\n"
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
            "☀️ 早安晨報：08:00（行程+天氣+待辦）\n"
            "⏰ 定時關心：12:00 / 16:00 / 23:00\n"
            "📝 到期提醒：09:00 / 20:00\n"
            "有什麼都可以跟Lumio說喔！"
        )

    return None  # 非指令


def handle_reset_memory(user_id: str) -> str:
    """清除對話記憶"""
    db.clear_history(user_id)
    return "🔄 對話記憶已清除～\nLumio 會重新認識你，但待辦事項不會受影響喔！"


def _parse_todo_input(text: str) -> tuple[str, str, str | None]:
    """解析待辦輸入，支援分類和到期日
    格式：/待辦 [#分類] [日期] 內容
    例如：/待辦 #工作 4/5 準備董事會簡報
          /待辦 #私人 買生日禮物
          /待辦 明天 交報告
    """
    import re
    content = text
    category = "一般"
    due_date = None

    # 提取分類 #xxx
    cat_match = re.match(r"#(\S+)\s+", content)
    if cat_match:
        category = cat_match.group(1)
        content = content[cat_match.end():]

    # 提取日期
    now = datetime.now(ZoneInfo("Asia/Taipei"))
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
        # 嘗試匹配 M/D 格式
        date_match = re.match(r"(\d{1,2})/(\d{1,2})\s+", content)
        if date_match:
            m, d = int(date_match.group(1)), int(date_match.group(2))
            year = now.year if m >= now.month else now.year + 1
            due_date = f"{year}-{m:02d}-{d:02d}"
            content = content[date_match.end():]

    return content.strip(), category, due_date


def handle_todo(text: str, user_id: str) -> str:
    """待辦事項完整處理（支援分類 + 到期日）"""
    t = text.strip()
    parts = t.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    # 查看清單
    if not arg:
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
                now = datetime.now(ZoneInfo("Asia/Taipei")).date()
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

    # 完成項目
    if arg.startswith("完成 ") or arg.startswith("done "):
        try:
            idx = int(arg.split()[1])
            name = db.complete_todo(user_id, idx)
            if name:
                return f"✅ 太棒了！「{name}」完成囉～"
            return "⚠️ 編號不對喔，用 /待辦 查看清單"
        except (ValueError, IndexError):
            return "⚠️ 用法：/待辦 完成 1"

    # 刪除項目
    if arg.startswith("刪除 ") or arg.startswith("del "):
        try:
            idx = int(arg.split()[1])
            name = db.delete_todo(user_id, idx)
            if name:
                return f"🗑 已刪除「{name}」"
            return "⚠️ 編號不對喔，用 /待辦 查看清單"
        except (ValueError, IndexError):
            return "⚠️ 用法：/待辦 刪除 1"

    # 清空
    if arg in ("清空", "clear"):
        db.clear_todos(user_id)
        return "🗑 待辦清單已清空～"

    # 新增項目（支援分類 + 到期日）
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
    """快速記事 / 備忘錄"""
    t = text.strip()
    parts = t.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    # 查看筆記
    if not arg:
        notes = db.get_notes(user_id)
        if not notes:
            return "📒 備忘錄是空的喔～\n用法：/記事 客戶說預算上限500萬"
        lines = ["📒 最近的備忘錄："]
        for i, (_id, content, created_at) in enumerate(notes, 1):
            time_str = created_at.strftime("%m/%d %H:%M") if hasattr(created_at, 'strftime') else str(created_at)[:16]
            lines.append(f"  {i}. {content}\n     🕐 {time_str}")
        return "\n".join(lines)

    # 刪除
    if arg.startswith("刪除 ") or arg.startswith("del "):
        try:
            idx = int(arg.split()[1])
            name = db.delete_note(user_id, idx)
            if name:
                return f"🗑 已刪除備忘：「{name}」"
            return "⚠️ 編號不對喔，用 /記事 查看清單"
        except (ValueError, IndexError):
            return "⚠️ 用法：/記事 刪除 1"

    # 清空
    if arg in ("清空", "clear"):
        db.clear_notes(user_id)
        return "🗑 備忘錄已清空～"

    # 新增
    count = db.add_note(user_id, arg)
    return f"📒 已記下：「{arg}」\n目前共 {count} 則備忘"


def handle_trip(text: str) -> str:
    """行程規劃助手"""
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
        # 先用 Perplexity 搜尋旅遊資訊
        search_result = web_search(f"{query} 行程推薦 景點美食")
        resp = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            system=(
                "你是大老闆的貼心秘書 Lumio，老闆要你幫忙規劃行程。"
                "請根據搜尋結果，整理出一份完整的行程表。\n"
                "格式要求：\n"
                "1. 按天數分段（Day 1、Day 2...）\n"
                "2. 每個時段標註時間和地點\n"
                "3. 包含景點、餐廳推薦\n"
                "4. 最後附上實用小提醒（交通、天氣、注意事項）\n"
                "重要：不要使用 Markdown 語法，用 emoji 和空行排版。"
                "語氣溫暖專業，像是真的幫老闆安排好了一切。"
            ),
            messages=[{"role": "user", "content": f"幫我規劃：{query}\n\n參考資訊：\n{search_result}"}],
        )
        return f"🧳 行程規劃好了～\n\n{resp.content[0].text}"
    except Exception as e:
        return f"⚠️ 行程規劃失敗：{e}"


# ─────────────────────────────────────────────
# 處理文字訊息
# ─────────────────────────────────────────────
@handler.add(MessageEvent, message=TextMessageContent)
def on_text(event: MessageEvent):
    text        = event.message.text
    user_id     = event.source.user_id
    source_type = event.source.type   # "user" | "group" | "room"

    # ── DEBUG：印出收到的訊息資訊 ──
    print(f"[DEBUG] source_type={source_type}, user_id={user_id}, text={text!r}")
    mention = getattr(event.message, "mention", None)
    print(f"[DEBUG] mention={mention}, BOT_USER_ID={BOT_USER_ID!r}")
    group_id = getattr(event.source, "group_id", None)
    print(f"[DEBUG] group_id={group_id}")

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)

        def reply(msg: str):
            try:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=msg)]
                    )
                )
                print(f"[DEBUG] 回覆成功：{msg[:30]}")
            except Exception as e:
                print(f"[DEBUG] 回覆失敗：{e}")

        # ── 指令優先（群組 & 私訊都支援）──
        t = text.strip()
        if t in ("/清除記憶", "/reset", "/清除"):
            reply(handle_reset_memory(user_id))
            return
        if t.startswith("/todo") or t.startswith("/待辦"):
            reply(handle_todo(text, user_id))
            return
        if t.startswith("/note") or t.startswith("/記事") or t.startswith("/備忘"):
            reply(handle_note(text, user_id))
            return
        cmd_reply = handle_command(text)
        if cmd_reply:
            reply(cmd_reply)
            return

        # ── 群組：只在被 @ 時才回應（暫時改為全部回應方便測試）──
        if source_type in ("group", "room"):
            # 暫時註解掉 mention 檢查，先確認 Claude 呼叫有沒有問題
            # mention = getattr(event.message, "mention", None)
            # if not mention:
            #     return
            pass  # 暫時全部回應

        # ── 呼叫 Claude ──
        try:
            answer = ask_claude(user_id, text)
            reply(answer)
        except Exception as e:
            print(f"[DEBUG] Claude 呼叫失敗：{e}")
            reply(f"⚠️ 發生錯誤：{e}")

# ─────────────────────────────────────────────
# 處理圖片訊息
# ─────────────────────────────────────────────
@handler.add(MessageEvent, message=ImageMessageContent)
def on_image(event: MessageEvent):
    user_id = event.source.user_id

    with ApiClient(configuration) as api_client:
        line_bot_api  = MessagingApi(api_client)
        line_bot_blob = MessagingApiBlob(api_client)

        def reply(msg: str):
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=msg)]
                )
            )

        try:
            raw        = line_bot_blob.get_message_content(event.message.id)
            image_b64  = base64.b64encode(raw).decode("utf-8")
            answer     = ask_claude(user_id, "", image_b64)
            reply(answer)
        except Exception as e:
            reply(f"⚠️ 圖片分析失敗：{e}")
