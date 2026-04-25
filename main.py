"""LINE AI Bot — Lumio（FastAPI 入口）"""
import base64
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from linebot.v3.messaging import (
    ApiClient, MessagingApi, MessagingApiBlob,
    ReplyMessageRequest, TextMessage,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent, FileMessageContent
from linebot.v3.exceptions import InvalidSignatureError

import db
import config
from config import line_config, webhook_handler as handler
from features.chat import ask_claude, analyze_file
from features.todo import handle_todo, handle_note, handle_reset_memory, handle_help
from features.calendar import handle_cal


# ── FastAPI Lifespan ──────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        with ApiClient(line_config) as api_client:
            profile = MessagingApi(api_client).get_bot_info()
            config.BOT_USER_ID = profile.user_id
            print(f"[Bot 啟動] Bot userId = {config.BOT_USER_ID}")
    except Exception as e:
        print(f"[警告] 無法取得 Bot userId: {e}")
    db.init_db()
    print("[Bot 啟動] 初始化完成")
    yield


app = FastAPI(lifespan=lifespan)


# ── 路由 ─────────────────────────────────────────


@app.get("/")
async def root():
    return {"status": "LINE AI Bot is running! ✅"}


@app.post("/webhook")
async def webhook(request: Request):
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    try:
        handler.handle(body.decode("utf-8"), signature)
    except InvalidSignatureError:
        return {"error": "Invalid signature"}, 400
    return {"status": "ok"}


# ── LINE 事件處理 ─────────────────────────────────


@handler.add(MessageEvent, message=TextMessageContent)
def on_text(event: MessageEvent):
    text = event.message.text
    user_id = event.source.user_id

    with ApiClient(line_config) as api_client:
        line_bot_api = MessagingApi(api_client)

        def reply(msg: str):
            try:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=msg)],
                    )
                )
            except Exception as e:
                print(f"[回覆失敗] {e}")

        t = text.strip()

        # ── 快捷指令（直接執行，不走 Claude）
        if t in ("/reset", "/清除記憶"):
            reply(handle_reset_memory(user_id))
        elif t.startswith("/待辦") or t.startswith("/t"):
            reply(handle_todo(t, user_id))
        elif t.startswith("/記事") or t.startswith("/備忘"):
            reply(handle_note(t, user_id))
        elif t.startswith("/日曆") or t.startswith("/cal"):
            reply(handle_cal(t))
        elif t in ("/h", "/help"):
            reply(handle_help())

        # ── 其他全走 Claude（自然語言處理）
        else:
            try:
                reply(ask_claude(user_id, t))
            except Exception as e:
                print(f"[Claude 錯誤] {e}")
                reply(f"⚠️ 發生錯誤：{e}")


@handler.add(MessageEvent, message=ImageMessageContent)
def on_image(event: MessageEvent):
    user_id = event.source.user_id

    with ApiClient(line_config) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_blob = MessagingApiBlob(api_client)

        def reply(msg: str):
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=msg)],
                )
            )

        try:
            raw = line_bot_blob.get_message_content(event.message.id)
            image_b64 = base64.b64encode(raw).decode("utf-8")
            reply(ask_claude(user_id, "", image_b64))
        except Exception as e:
            reply(f"⚠️ 圖片分析失敗：{e}")


@handler.add(MessageEvent, message=FileMessageContent)
def on_file(event: MessageEvent):
    user_id = event.source.user_id
    filename = event.message.file_name or "document"
    file_size = event.message.file_size or 0

    with ApiClient(line_config) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_blob = MessagingApiBlob(api_client)

        def reply(msg: str):
            try:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=msg)],
                    )
                )
            except Exception as e:
                print(f"[回覆失敗] {e}")

        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
        if ext not in ("pdf", "txt", "md", "csv"):
            reply(f"⚠️ 目前支援 PDF、TXT、MD、CSV 格式\n收到的是：{filename}")
            return

        if file_size > 20 * 1024 * 1024:
            reply(f"⚠️ 檔案太大（{file_size/1024/1024:.1f}MB），請上傳 20MB 以下的文件")
            return

        try:
            raw = bytes(line_bot_blob.get_message_content(event.message.id))
            reply(analyze_file(user_id, raw, filename))
        except Exception as e:
            print(f"[文件分析錯誤] {e}")
            reply(f"⚠️ 文件分析失敗：{e}")
