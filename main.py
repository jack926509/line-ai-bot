"""LINE AI Bot — Lumio 大老闆的貼心秘書（FastAPI 入口）"""
import base64
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from linebot.v3.messaging import (
    ApiClient, MessagingApi, MessagingApiBlob,
    ReplyMessageRequest, TextMessage,
)
from linebot.v3.webhooks import (
    MessageEvent, TextMessageContent, ImageMessageContent,
)
from linebot.v3.exceptions import InvalidSignatureError
from apscheduler.triggers.cron import CronTrigger

import db
import config
from config import (
    line_config, webhook_handler as handler,
    anthropic_client, scheduler,
    CLAUDE_MODEL, TZ_NAME, GROUP_ID,
)
from prompts import build_system_prompt
from services import TOOLS, dispatch_tool
from commands import handle_command, handle_reset_memory, handle_todo, handle_note
from scheduler import (
    send_morning_briefing, send_scheduled_message,
    check_due_reminders, SCHEDULED_MESSAGES,
)


# ─── Claude 對話（支援圖片 + 工具呼叫）───


def ask_claude(user_id: str, text: str, image_b64: str | None = None) -> str:
    if image_b64:
        content = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_b64}},
            {"type": "text", "text": text or "請用繁體中文分析這張圖片"},
        ]
    else:
        content = text

    db.save_message(user_id, "user", content)
    messages = db.get_history(user_id)
    system_prompt = build_system_prompt()

    response = anthropic_client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1000,
        system=system_prompt,
        tools=TOOLS,
        messages=messages,
    )

    # 處理 tool use（最多 3 輪）
    for _ in range(3):
        if response.stop_reason != "tool_use":
            break
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                result = dispatch_tool(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": tool_results})
        response = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
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
    db.save_message(user_id, "assistant", reply)
    return reply


# ─── FastAPI Lifespan ───


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 取得 Bot userId
    try:
        with ApiClient(line_config) as api_client:
            profile = MessagingApi(api_client).get_bot_info()
            config.BOT_USER_ID = profile.user_id
            print(f"[Bot 啟動] Bot userId = {config.BOT_USER_ID}")
    except Exception as e:
        print(f"[警告] 無法取得 Bot userId: {e}")

    db.init_db()

    # 啟動排程
    if GROUP_ID:
        scheduler.add_job(
            send_morning_briefing,
            CronTrigger(hour=8, minute=0, timezone=TZ_NAME),
            id="morning_briefing",
        )
        for slot, cfg in SCHEDULED_MESSAGES.items():
            scheduler.add_job(
                send_scheduled_message,
                CronTrigger(hour=cfg["hour"], minute=cfg["minute"], timezone=TZ_NAME),
                args=[slot],
                id=f"scheduled_{slot}",
            )
        for h in (9, 20):
            scheduler.add_job(
                check_due_reminders,
                CronTrigger(hour=h, minute=0, timezone=TZ_NAME),
                id=f"due_reminder_{h}",
            )
    scheduler.start()
    print("[排程] 啟動完成（晨報 08:00 / 推播 12:00+16:00+23:00 / 到期提醒 09:00+20:00）")

    yield

    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


# ─── 路由 ───


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


# ─── LINE 事件處理 ───


@handler.add(MessageEvent, message=TextMessageContent)
def on_text(event: MessageEvent):
    text = event.message.text
    user_id = event.source.user_id
    source_type = event.source.type

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

        # 指令優先
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

        # 群組：暫時全部回應
        if source_type in ("group", "room"):
            pass

        # 呼叫 Claude
        try:
            answer = ask_claude(user_id, text)
            reply(answer)
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
            answer = ask_claude(user_id, "", image_b64)
            reply(answer)
        except Exception as e:
            reply(f"⚠️ 圖片分析失敗：{e}")
