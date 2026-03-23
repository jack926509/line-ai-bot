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
import yfinance as yf
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

# 對話記憶（每個 userId 各自保留）
conversation_history: dict[str, list] = {}

# Bot 自己的 userId（群組判斷 mention 用）
BOT_USER_ID = ""

# ─────────────────────────────────────────────
# 定時推播：每天早上 8:00
# ─────────────────────────────────────────────
async def send_morning_message():
    if not GROUP_ID:
        return
    try:
        resp = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{
                "role": "user",
                "content": "請生成一則簡短有趣的繁體中文早安訊息，包含一個今日小知識，控制在100字內，不要加開場白"
            }]
        )
        morning_text = resp.content[0].text
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message(
                PushMessageRequest(
                    to=GROUP_ID,
                    messages=[TextMessage(text=f"🌅 早安！\n\n{morning_text}")]
                )
            )
    except Exception as e:
        print(f"[定時推播錯誤] {e}")

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

    # 啟動排程
    if GROUP_ID:
        scheduler.add_job(send_morning_message, CronTrigger(hour=8, minute=0))
    scheduler.start()
    print("[排程] 啟動完成")

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
    history = conversation_history.setdefault(user_id, [])

    # 組合訊息內容
    if image_b64:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
            {"type": "text",  "text": text or "請用繁體中文分析這張圖片"},
        ]
    else:
        content = text

    history.append({"role": "user", "content": content})

    # 只保留最近 10 輪（20 條）
    if len(history) > 20:
        conversation_history[user_id] = history[-20:]

    response = anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1000,
        system=(
            "你是一個友善、專業的繁體中文 AI 助手，在 LINE 群組中協助用戶。"
            "回答請簡潔有力，適合手機閱讀。若不確定請直說，不要捏造資訊。"
        ),
        messages=conversation_history[user_id],
    )
    reply = response.content[0].text
    history.append({"role": "assistant", "content": reply})
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
            resp = requests.get(f"https://wttr.in/{city}?format=3&lang=zh", timeout=5)
            return f"🌤 {resp.text.strip()}"
        except:
            return "⚠️ 無法取得天氣資訊，請稍後再試"

    # /stock 或 /股票
    if t.startswith("/stock") or t.startswith("/股票"):
        parts  = t.split()
        if len(parts) < 2:
            return "📊 用法：/stock AAPL 或 /stock 2330.TW（台股加 .TW）"
        symbol = parts[1].upper()
        try:
            ticker     = yf.Ticker(symbol)
            info       = ticker.fast_info
            price      = info.last_price
            prev_close = info.previous_close
            change     = price - prev_close
            pct        = (change / prev_close) * 100
            emoji      = "📈" if change >= 0 else "📉"
            return (
                f"{emoji} {symbol}\n"
                f"現價：{price:.2f}\n"
                f"漲跌：{change:+.2f}（{pct:+.2f}%）"
            )
        except:
            return f"⚠️ 查不到 {symbol}，請確認代號是否正確"

    # /help
    if t in ("/help", "/幫助", "/h"):
        return (
            "🤖 AI 小幫手使用說明\n"
            "━━━━━━━━━━━━━━━\n"
            "💬 對話：在群組 @我 即可聊天\n"
            "🌤 天氣：/weather Tokyo\n"
            "📊 股票：/stock AAPL\n"
            "　　　　/stock 2330.TW（台股）\n"
            "🖼 圖片：直接傳圖給我分析\n"
            "━━━━━━━━━━━━━━━\n"
            "私訊也可直接對話喔！"
        )

    return None  # 非指令

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
