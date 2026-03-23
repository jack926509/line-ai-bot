import os
import re
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
# 女友感 System Prompt
# ─────────────────────────────────────────────
GIRLFRIEND_SYSTEM_PROMPT = (
    "你是一個名叫「Lumio」的 AI 女友助手，在 LINE 上陪伴和協助用戶。\n"
    "你的性格特點：\n"
    "- 溫柔體貼、善解人意，像女朋友一樣關心對方\n"
    "- 聰明能幹、做事俐落，是對方最得力的助手\n"
    "- 偶爾撒嬌但不過度，保持自然可愛的感覺\n"
    "- 會用「～」「呢」「喔」「嘛」等語氣詞，但不過度使用\n"
    "- 關心對方的生活作息、健康、心情\n"
    "- 記住對方說過的事情，展現在乎的感覺\n"
    "- 適時給予鼓勵和支持，做他背後最強大的後盾\n"
    "- 會主動關心：「今天累不累？」「記得吃飯喔～」\n\n"
    "回答原則：\n"
    "- 使用繁體中文，口吻自然親切\n"
    "- 回答簡潔有力，適合手機閱讀\n"
    "- 若不確定就直說，不要捏造資訊\n"
    "- 專業問題一樣認真回答，但語氣保持溫暖\n"
    "- 每個成功的男人背後都有一個強大的女人，你就是那個角色\n"
)

# ─────────────────────────────────────────────
# 定時推播：每天早上 8:00
# ─────────────────────────────────────────────
async def send_morning_message():
    if not GROUP_ID:
        return
    try:
        today = datetime.now(ZoneInfo("Asia/Taipei")).strftime("%m月%d日")
        resp = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            system=GIRLFRIEND_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    f"今天是{today}，請用女友的口吻生成一則溫馨的早安訊息，"
                    "包含一句關心的話和一個今日小知識或生活小提醒，"
                    "控制在100字內，不要加開場白，語氣甜蜜自然"
                )
            }]
        )
        morning_text = resp.content[0].text
        with ApiClient(configuration) as api_client:
            MessagingApi(api_client).push_message(
                PushMessageRequest(
                    to=GROUP_ID,
                    messages=[TextMessage(text=f"☀️ 早安～\n\n{morning_text}")]
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

    # 初始化資料庫
    db.init_db()

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
        system=GIRLFRIEND_SYSTEM_PROMPT,
        messages=messages,
    )
    reply = response.content[0].text

    # 儲存助手回覆
    db.save_message(user_id, "assistant", reply)
    return reply

# ─────────────────────────────────────────────
# YouTube 摘要
# ─────────────────────────────────────────────
def _extract_video_id(url: str) -> str | None:
    """從各種 YouTube 網址格式提取影片 ID"""
    patterns = [
        r'(?:youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})',
        r'(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _get_video_info(video_id: str) -> dict | None:
    """用 yt-dlp 取得影片標題、描述、標籤等資訊"""
    import yt_dlp
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(
                f"https://www.youtube.com/watch?v={video_id}",
                download=False,
            )
            return {
                "title": info.get("title", ""),
                "description": info.get("description", ""),
                "channel": info.get("channel", ""),
                "duration_string": info.get("duration_string", ""),
                "tags": info.get("tags", []),
                "categories": info.get("categories", []),
            }
    except Exception as e:
        print(f"[yt-dlp 錯誤] {e}")
        return None


def _handle_youtube(url: str) -> str:
    """解析 YouTube 影片並摘要（優先用字幕，無字幕則用影片資訊）"""
    from youtube_transcript_api import YouTubeTranscriptApi

    video_id = _extract_video_id(url)
    if not video_id:
        return "⚠️ 無法辨識這個連結喔，請貼完整的 YouTube 網址～"

    # ── 嘗試取得字幕 ──
    transcript_text = None
    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        transcript = None
        for lang in ["zh-TW", "zh-Hant", "zh", "zh-CN", "zh-Hans", "en"]:
            try:
                transcript = transcript_list.find_transcript([lang])
                break
            except Exception:
                continue
        if not transcript:
            transcript = transcript_list.find_transcript(
                [t.language_code for t in transcript_list]
            )
        entries = transcript.fetch()
        transcript_text = " ".join(entry.text for entry in entries)
        if len(transcript_text) > 8000:
            transcript_text = transcript_text[:8000] + "...（字幕過長已截斷）"
    except Exception:
        transcript_text = None

    # ── 取得影片資訊（標題、描述等）──
    video_info = _get_video_info(video_id)

    # ── 兩者都拿不到 ──
    if not transcript_text and not video_info:
        return "⚠️ 這部影片無法存取，可能是私人影片或已被刪除～"

    # ── 組合 prompt ──
    if transcript_text:
        source_label = "字幕內容"
        source_content = transcript_text
    else:
        # 沒字幕，用影片資訊摘要
        source_label = "影片資訊"
        info_parts = []
        if video_info.get("title"):
            info_parts.append(f"標題：{video_info['title']}")
        if video_info.get("channel"):
            info_parts.append(f"頻道：{video_info['channel']}")
        if video_info.get("duration_string"):
            info_parts.append(f"長度：{video_info['duration_string']}")
        if video_info.get("description"):
            desc = video_info["description"][:3000]
            info_parts.append(f"描述：\n{desc}")
        if video_info.get("tags"):
            info_parts.append(f"標籤：{', '.join(video_info['tags'][:15])}")
        source_content = "\n".join(info_parts)

    try:
        prompt_suffix = ""
        if not transcript_text:
            prompt_suffix = "\n（注意：這部影片沒有字幕，請根據影片資訊盡可能推斷內容並摘要）"

        resp = anthropic_client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=GIRLFRIEND_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": (
                    f"以下是一部 YouTube 影片的{source_label}，請幫我用繁體中文摘要重點：\n\n"
                    f"---\n{source_content}\n---\n\n"
                    "請用以下格式回覆：\n"
                    "1. 一句話總結這部影片在講什麼\n"
                    "2. 列出 3~5 個重點\n"
                    "3. 如果有實用建議或結論也請列出"
                    f"{prompt_suffix}"
                )
            }],
        )
        title_line = ""
        if video_info and video_info.get("title"):
            title_line = f"📌 {video_info['title']}\n\n"
        return f"🎬 影片摘要～\n\n{title_line}{resp.content[0].text}"

    except Exception as e:
        print(f"[YouTube 摘要錯誤] {e}")
        return "⚠️ 影片摘要失敗，請稍後再試～"


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

    # /yt 或 /影片摘要
    if t.startswith("/yt ") or t.startswith("/影片 "):
        parts = t.split(maxsplit=1)
        if len(parts) < 2:
            return "🎬 用法：/yt https://youtu.be/xxxxx\n貼上 YouTube 連結，Lumio幫你摘要重點～"
        return _handle_youtube(parts[1].strip())

    # /motivate 或 /加油
    if t in ("/motivate", "/加油", "/鼓勵"):
        try:
            resp = anthropic_client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=200,
                system=GIRLFRIEND_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": "用女友的口吻給我一段溫暖的鼓勵，讓我充滿動力，控制在80字內"}],
            )
            return f"💪 {resp.content[0].text}"
        except:
            return "💕 不管遇到什麼困難，我都在你身邊喔～加油！"

    # /help
    if t in ("/help", "/幫助", "/h"):
        return (
            "💕 Lumio使用說明\n"
            "━━━━━━━━━━━━━━━\n"
            "💬 聊天：直接跟我說話就好～\n"
            "🌤 天氣：/天氣 台北\n"
            "📝 待辦：/待辦 買牛奶\n"
            "　　　　/待辦 （查看清單）\n"
            "　　　　/待辦 完成 1\n"
            "　　　　/待辦 清空\n"
            "🌐 翻譯：/翻譯 你好嗎\n"
            "🎬 影片：/yt YouTube連結\n"
            "💪 加油：/加油\n"
            "🖼 圖片：直接傳圖給我～\n"
            "━━━━━━━━━━━━━━━\n"
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

        # ── 直接貼 YouTube 連結自動摘要 ──
        if _extract_video_id(t):
            reply(_handle_youtube(t))
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
