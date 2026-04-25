"""LINE AI Bot — Lumio（FastAPI 入口）"""
import base64
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from linebot.v3.messaging import ReplyMessageRequest, TextMessage
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent, FileMessageContent
from linebot.v3.exceptions import InvalidSignatureError

import db
import config
from config import (
    logger, line_bot_api, line_bot_blob,
    webhook_handler as handler,
)
from features.chat import ask_claude, analyze_file
from features.todo import handle_todo, handle_note, handle_reset_memory, handle_help
from features.calendar import handle_cal
from features.briefing import build_morning_briefing
from features.url_summary import summarize_url
from features.scheduler import start_scheduler, shutdown_scheduler


# ── FastAPI Lifespan ──────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        profile = line_bot_api.get_bot_info()
        config.BOT_USER_ID = profile.user_id
        logger.info(f"Bot 啟動 userId={config.BOT_USER_ID}")
    except Exception as e:
        logger.warning(f"無法取得 Bot userId: {e}")
    db.init_db()
    start_scheduler()
    logger.info("Bot 啟動初始化完成")
    yield
    shutdown_scheduler()


app = FastAPI(lifespan=lifespan)


# ── 路由 ─────────────────────────────────────────


@app.get("/")
async def root():
    return {"status": "LINE AI Bot is running! ✅"}


def _handle_webhook_safe(body: str, signature: str) -> None:
    """背景任務包裝：捕捉所有例外避免靜默失敗"""
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.warning("Webhook 簽章驗證失敗")
    except Exception as e:
        logger.exception(f"Webhook 處理錯誤: {e}")


@app.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    signature = request.headers.get("X-Line-Signature", "")
    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature")
    body = (await request.body()).decode("utf-8")
    background_tasks.add_task(_handle_webhook_safe, body, signature)
    return {"status": "ok"}


# ── LINE 事件處理 ─────────────────────────────────


def _reply(reply_token: str, msg: str) -> None:
    try:
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[TextMessage(text=msg)])
        )
    except Exception as e:
        logger.warning(f"LINE 回覆失敗: {e}")


def _build_status(user_id: str) -> str:
    sub = db.get_subscription(user_id)
    todos = db.get_todos(user_id)
    notes = db.get_notes(user_id)
    if not sub:
        sub_line = "☀️ 早晨簡報：未訂閱（首次互動將自動開啟）"
    else:
        on = "開啟" if sub["briefing"] else "關閉"
        sub_line = f"☀️ 早晨簡報：{on}（每日 {sub['brief_time']}）"
    return (
        "📊 Lumio 狀態\n"
        "━━━━━━━━━━━\n"
        f"{sub_line}\n"
        f"📝 待辦：{sum(1 for t in todos if not t[2])} 項未完成 / 共 {len(todos)}\n"
        f"📒 備忘：{len(notes)} 則"
    )


@handler.add(MessageEvent, message=TextMessageContent)
def on_text(event: MessageEvent):
    text = event.message.text
    user_id = event.source.user_id
    t = text.strip()

    # 自動註冊訂閱（任何訊息均觸發）
    db.upsert_subscription(user_id)

    # ── 快捷指令（直接執行，不走 Claude）
    if t in ("/reset", "/清除記憶"):
        _reply(event.reply_token, handle_reset_memory(user_id))
    elif t == "/簡報":
        _reply(event.reply_token, build_morning_briefing(user_id))
    elif t in ("/簡報 開", "/簡報開"):
        db.set_briefing(user_id, True)
        _reply(event.reply_token, "✅ 早晨簡報已開啟（每日 08:00 推送）")
    elif t in ("/簡報 關", "/簡報關"):
        db.set_briefing(user_id, False)
        _reply(event.reply_token, "🔕 早晨簡報已關閉")
    elif t in ("/狀態", "/status"):
        _reply(event.reply_token, _build_status(user_id))
    elif t.startswith("/摘要 ") or t.startswith("/摘要\n"):
        url = t[3:].strip()
        _reply(event.reply_token, summarize_url(url))
    elif t.startswith("/待辦") or t.startswith("/t"):
        _reply(event.reply_token, handle_todo(t, user_id))
    elif t.startswith("/記事") or t.startswith("/備忘"):
        _reply(event.reply_token, handle_note(t, user_id))
    elif t.startswith("/日曆") or t.startswith("/cal"):
        _reply(event.reply_token, handle_cal(t))
    elif t in ("/h", "/help"):
        _reply(event.reply_token, handle_help())
    else:
        try:
            _reply(event.reply_token, ask_claude(user_id, t))
        except Exception as e:
            logger.exception(f"Claude 呼叫錯誤: {e}")
            _reply(event.reply_token, f"⚠️ 發生錯誤：{e}")


@handler.add(MessageEvent, message=ImageMessageContent)
def on_image(event: MessageEvent):
    user_id = event.source.user_id
    db.upsert_subscription(user_id)
    try:
        raw = line_bot_blob.get_message_content(event.message.id)
        image_b64 = base64.b64encode(raw).decode("utf-8")
        _reply(event.reply_token, ask_claude(user_id, "", image_b64))
    except Exception as e:
        logger.exception(f"圖片分析錯誤: {e}")
        _reply(event.reply_token, f"⚠️ 圖片分析失敗：{e}")


@handler.add(MessageEvent, message=FileMessageContent)
def on_file(event: MessageEvent):
    user_id = event.source.user_id
    db.upsert_subscription(user_id)
    filename = event.message.file_name or "document"
    file_size = event.message.file_size or 0

    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext not in ("pdf", "txt", "md", "csv"):
        _reply(event.reply_token, f"⚠️ 目前支援 PDF、TXT、MD、CSV 格式\n收到的是：{filename}")
        return

    if file_size > 20 * 1024 * 1024:
        _reply(event.reply_token, f"⚠️ 檔案太大（{file_size/1024/1024:.1f}MB），請上傳 20MB 以下的文件")
        return

    try:
        raw = bytes(line_bot_blob.get_message_content(event.message.id))
        _reply(event.reply_token, analyze_file(user_id, raw, filename))
    except Exception as e:
        logger.exception(f"文件分析錯誤: {e}")
        _reply(event.reply_token, f"⚠️ 文件分析失敗：{e}")
