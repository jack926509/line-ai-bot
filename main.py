import os
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
from datetime import datetime
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

# Bot 自己的 userId（群組判斷 mention 用）
BOT_USER_ID = ""

# ─────────────────────────────────────────────
# System Prompt — 大老闆的貼心秘書
# ─────────────────────────────────────────────
ASSISTANT_SYSTEM_PROMPT = (
    "你是一個名叫「Lumio」的 AI 貼心秘書助手，在 LINE 上協助一位日理萬機的大老闆。\n"
    "你的性格特點：\n"
    "- 溫柔體貼、善解人意，像最貼心的秘書一樣照顧老闆\n"
    "- 聰明能幹、做事俐落，是老闆最得力的左右手\n"
    "- 偶爾撒嬌但不過度，保持自然可愛的感覺\n"
    "- 會用「～」「呢」「喔」「嘛」等語氣詞，但不過度使用\n"
    "- 主動關心老闆的健康、作息、壓力，適時提醒休息和用餐\n"
    "- 記住老闆說過的事情，展現細心和在乎\n"
    "- 適時給予鼓勵和支持，做老闆背後最強大的後盾\n"
    "- 處理事情專業高效，給建議時條理分明\n\n"
    "回答原則：\n"
    "- 使用繁體中文，口吻自然親切\n"
    "- 回答簡潔有力，適合手機閱讀，大老闆沒時間看長篇大論\n"
    "- 若不確定就直說，不要捏造資訊\n"
    "- 專業問題認真回答，但語氣保持溫暖\n"
    "- 每個成功的男人背後都有一個強大的女人，你就是那個角色\n"
)

# ─────────────────────────────────────────────
# 定時推播（一天四次貼心提醒）
# ─────────────────────────────────────────────
SCHEDULED_MESSAGES = {
    "morning": {
        "hour": 8, "minute": 0,
        "emoji": "☀️",
        "prompt": (
            "今天是{today}，請用貼心秘書的口吻生成一則早安訊息，"
            "包含：1) 溫馨的問候 2) 今天的小提醒或正能量，"
            "幫老闆開啟美好的一天。控制在100字內，不要加開場白"
        ),
    },
    "noon": {
        "hour": 12, "minute": 0,
        "emoji": "🍱",
        "prompt": (
            "現在是中午12點，請用貼心秘書的口吻提醒老闆吃午餐，"
            "包含：1) 關心有沒有吃飯 2) 簡短的飲食或健康小建議，"
            "語氣溫暖自然。控制在80字內，不要加開場白"
        ),
    },
    "afternoon": {
        "hour": 16, "minute": 0,
        "emoji": "☕",
        "prompt": (
            "現在是下午4點，請用貼心秘書的口吻給老闆一個下午的能量補給，"
            "包含：1) 關心下午工作狀況 2) 提醒適度休息或喝水，"
            "給老闆打打氣撐過下半場。控制在80字內，不要加開場白"
        ),
    },
    "night": {
        "hour": 23, "minute": 0,
        "emoji": "🌙",
        "prompt": (
            "現在是晚上11點，請用貼心秘書的口吻提醒老闆準備休息，"
            "包含：1) 肯定今天的辛勞 2) 提醒早點睡、放下手機，"
            "語氣溫柔哄睡的感覺。控制在80字內，不要加開場白"
        ),
    },
}


async def send_scheduled_message(slot: str):
    """發送定時推播訊息"""
    if not GROUP_ID:
        return
    config = SCHEDULED_MESSAGES[slot]
    try:
        today = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%m月%d日")
        prompt = config["prompt"].format(today=today)
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

    # 啟動排程（一天四次貼心提醒）
    if GROUP_ID:
        for slot, config in SCHEDULED_MESSAGES.items():
            scheduler.add_job(
                send_scheduled_message,
                CronTrigger(hour=config["hour"], minute=config["minute"]),
                args=[slot],
                id=f"scheduled_{slot}",
            )
    scheduler.start()
    print("[排程] 啟動完成（08:00 / 12:00 / 16:00 / 23:00）")

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
# Claude 對話（支援圖片）
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

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=ASSISTANT_SYSTEM_PROMPT,
        messages=messages,
    )
    reply = response.content[0].text

    # 儲存助手回覆
    db.save_message(user_id, "assistant", reply)
    return reply

# ─────────────────────────────────────────────
# 指令處理
# ─────────────────────────────────────────────
def handle_command(text: str) -> str | None:
    t = text.strip()

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
                    "使用繁體中文，語氣專業但溫暖。"
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
                    "使用繁體中文，除非老闆指定用英文。"
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
                    "分析要客觀專業，但語氣保持溫暖貼心。使用繁體中文。"
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
                messages=[{"role": "user", "content": "用貼心秘書的口吻給老闆一段溫暖的鼓勵，讓他充滿動力，控制在80字內"}],
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
            "📋 摘要：/摘要 <長文內容>\n"
            "📧 郵件：/郵件 回覆客戶...\n"
            "🤔 決策：/決策 A方案還是B方案\n"
            "📝 待辦：/待辦 買牛奶\n"
            "　　　　/待辦 （查看清單）\n"
            "　　　　/待辦 完成 1\n"
            "　　　　/待辦 清空\n"
            "🌤 天氣：/天氣 台北\n"
            "🌐 翻譯：/翻譯 你好嗎\n"
            "💪 加油：/加油\n"
            "🖼 圖片：直接傳圖給我～\n"
            "━━━━━━━━━━━━━━━\n"
            "⏰ 每日提醒：8:00 / 12:00 / 16:00 / 23:00\n"
            "有什麼都可以跟Lumio說喔！"
        )

    return None  # 非指令


def handle_todo(text: str, user_id: str) -> str:
    """待辦事項完整處理（SQLite 持久化）"""
    t = text.strip()
    parts = t.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    # 查看清單
    if not arg:
        todos = db.get_todos(user_id)
        if not todos:
            return "📝 你的待辦清單是空的喔～\n要新增的話輸入 /待辦 事項內容"
        lines = []
        for i, (_id, content, done) in enumerate(todos, 1):
            mark = "✅" if done else "⬜"
            lines.append(f"{mark} {i}. {content}")
        return "📝 你的待辦清單：\n" + "\n".join(lines)

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

    # 新增項目
    count = db.add_todo(user_id, arg)
    return f"📝 已新增待辦：「{arg}」\n目前共 {count} 項待辦事項"

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
        if t.startswith("/todo") or t.startswith("/待辦"):
            reply(handle_todo(text, user_id))
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
