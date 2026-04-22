"""LINE AI Bot — Lumio 大老闆的貼心秘書（FastAPI 入口）"""
import re
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

import db
import config
from config import (
    line_config, webhook_handler as handler,
    anthropic_client,
    CLAUDE_MODEL, TZ_NAME,
)
from prompts import build_system_prompt
from services import TOOLS, dispatch_tool
from commands import handle_command, handle_reset_memory, handle_todo, handle_note


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
    reply = _strip_markdown(reply)
    db.save_message(user_id, "assistant", reply)
    return reply


def _strip_markdown(text: str) -> str:
    """移除 LINE 不支援的 Markdown 語法"""
    # **粗體** / __粗體__ → 粗體
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    # *斜體* / _斜體_ （但不影響 emoji 旁的 _ 或 URL 中的 _）
    text = re.sub(r'(?<!\w)\*([^*\n]+?)\*(?!\w)', r'\1', text)
    # # 標題
    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
    # [文字](連結) → 文字\n連結
    text = re.sub(r'\[([^\]]+?)\]\((https?://[^\)]+)\)', r'\1\n\2', text)
    # `程式碼` → 程式碼
    text = re.sub(r'`([^`]+?)`', r'\1', text)
    return text


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
    print("[Bot 啟動] 初始化完成")

    yield


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
