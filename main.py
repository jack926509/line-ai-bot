"""LINE AI Bot — Lumio（FastAPI 入口）"""
import base64
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, BackgroundTasks, HTTPException
from linebot.v3.messaging import ReplyMessageRequest, TextMessage, FlexMessage
from linebot.v3.webhooks import (
    MessageEvent, TextMessageContent, ImageMessageContent, FileMessageContent,
    AudioMessageContent, PostbackEvent,
)
from linebot.v3.exceptions import InvalidSignatureError

import db
import config
from config import (
    logger, line_bot_api, line_bot_blob,
    webhook_handler as handler,
)
from features.chat import ask_claude, analyze_file
from features.todo import handle_todo, todo_complete, todo_delete
from features.note import handle_note, note_delete
from features.help import handle_reset_memory, handle_help
from features.calendar import handle_cal
from features.briefing import build_morning_briefing
from features.url_summary import summarize_url
from features.scheduler import start_scheduler, shutdown_scheduler
from features.doc_official import handle_template
from features.law import law_search
from features.trip import handle_trip
from features.meeting import analyze_meeting_file
from features.push import push_text
from features.flex import (
    todo_carousel, note_carousel, expense_carousel, expense_summary_bubble,
    parse_postback,
)
from features.audio import transcribe
from features.expense import (
    handle_expense, expense_delete, label_period, _today,
)


# ── Reply token / Rate limit ─────────────────────
# LINE reply token TTL 約 30s，留 5s buffer 改走 push
_REPLY_TTL_SECONDS = 25.0
# 單使用者每分鐘訊息上限（單 worker 部署，記憶體計數即可）
_RATE_LIMIT_WINDOW = 60.0
_RATE_LIMIT_MAX = 15
_user_hits: dict[str, deque] = defaultdict(deque)


def _rate_limited(user_id: str) -> bool:
    if not user_id:
        return False
    now = time.monotonic()
    q = _user_hits[user_id]
    while q and now - q[0] > _RATE_LIMIT_WINDOW:
        q.popleft()
    if len(q) >= _RATE_LIMIT_MAX:
        return True
    q.append(now)
    return False


def _is_duplicate(message_id: str) -> bool:
    """LINE webhook 重送去重：mark_processed 利用 PRIMARY KEY 原子寫入，
    回傳 False 代表已存在 → 略過。"""
    if not message_id:
        return False
    try:
        return not db.mark_processed(message_id)
    except Exception as e:
        # DB 故障時不阻擋訊息（fail-open），僅記錄
        logger.warning(f"idempotency check 失敗（fail-open）: {e}")
        return False


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


@app.get("/healthz")
async def healthz():
    """輕量健康檢查：DB 連線可達 + Bot userId 已取得 + scheduler 狀態。

    回傳 200 + JSON。任何子項失敗時對應欄位為 false 但仍回 200，
    讓上游監控自行判讀（相較硬性 500 更利於故障排除）。
    """
    checks: dict = {}
    # DB
    try:
        with db.get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        checks["db"] = True
    except Exception as e:
        logger.warning(f"healthz DB 檢查失敗: {e}")
        checks["db"] = False
    # Bot userId（lifespan 啟動時設定）
    checks["bot_user_id"] = bool(config.BOT_USER_ID)
    # Scheduler
    try:
        from features.scheduler import _scheduler
        checks["scheduler"] = bool(_scheduler and _scheduler.running)
    except Exception:
        checks["scheduler"] = False
    overall = "ok" if all(checks.values()) else "degraded"
    return {"status": overall, "checks": checks}


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


def _send(reply_token: str, user_id: str, msg, started_at: float | None = None) -> None:
    """先嘗試 reply；若 token 已逼近 TTL 或回覆失敗，自動 fallback 到 Push API。

    msg 可為 str（文字訊息）或 FlexMessage（互動式卡片）。
    Flex 因 push 走另一條路徑（push_text 僅支援文字），fallback 時改回送 alt_text。
    """
    is_flex = isinstance(msg, FlexMessage)
    fallback_text = msg.alt_text if is_flex else msg

    if started_at is not None and time.monotonic() - started_at > _REPLY_TTL_SECONDS:
        logger.info(f"reply_token 逼近 TTL，改用 push user={user_id}")
        push_text(user_id, fallback_text)
        return
    try:
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=[msg if is_flex else TextMessage(text=msg)])
        )
    except Exception as e:
        logger.warning(f"LINE reply 失敗，改用 push: {e}")
        if user_id:
            push_text(user_id, fallback_text)


def _todo_response(t: str, user_id: str):
    """`/待辦` 純列表時回 Flex carousel；其餘子指令（新增/完成/刪除）走文字。"""
    parts = t.strip().split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""
    if not arg:
        flex = todo_carousel(db.get_todos(user_id))
        if flex is not None:
            return flex
        # 空清單走文字（含說明）
    return handle_todo(t, user_id)


def _note_response(t: str, user_id: str):
    parts = t.strip().split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""
    if not arg:
        flex = note_carousel(db.get_notes(user_id))
        if flex is not None:
            return flex
    return handle_note(t, user_id)


def _expense_response(t: str, user_id: str):
    """`/記帳` 純列表 → 今日 Flex carousel；`/記帳 月/週/上月/年` → 統計 Flex；其餘走文字。"""
    parts = t.strip().split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        # 預設今日列表
        today = _today()
        rows = db.list_expenses(user_id, today, today, limit=20)
        flex = expense_carousel(rows, title=f"💰 今日（{today}）")
        if flex is not None:
            return flex
        return f"📭 今日（{today}）尚無記錄\n直接說「午餐 120」即可記帳"

    period_map = {
        "月": "month", "本月": "month", "上月": "last_month",
        "週": "week", "本週": "week", "年": "year", "今年": "year",
        "今日": "today", "昨日": "yesterday",
    }
    if arg in period_map:
        period = period_map[arg]
        sd, ed = _period_range(period)
        summary = db.expense_summarize(user_id, sd, ed)
        if summary["count"] > 0:
            return expense_summary_bubble(summary, label_period(period), sd, ed)
        # 空也走文字回覆友善訊息
        return f"📭 {label_period(period)}（{sd}~{ed}）尚無記錄"

    # 其他子指令（查 / 刪 / 清單 / 說明）走文字
    return handle_expense(t, user_id)


def _period_range(period: str):
    """同 features.expense.expense_summary 的期間切片，但回 (sd, ed) 給 Flex 統計用。"""
    today = _today()
    if period == "today":
        return today, today
    if period == "yesterday":
        from datetime import timedelta
        d = today - timedelta(days=1)
        return d, d
    if period == "week":
        from datetime import timedelta
        return today - timedelta(days=today.weekday()), today
    if period == "month":
        return today.replace(day=1), today
    if period == "last_month":
        from datetime import timedelta
        first = today.replace(day=1)
        ed = first - timedelta(days=1)
        return ed.replace(day=1), ed
    if period == "year":
        return today.replace(month=1, day=1), today
    return today, today


def _build_status(user_id: str) -> str:
    sub = db.get_subscription(user_id)
    todos = db.get_todos(user_id)
    notes = db.get_notes(user_id)
    if not sub:
        sub_line = "☀️ 早晨簡報：未訂閱（首次互動將自動開啟）"
    else:
        on = "開啟" if sub["briefing"] else "關閉"
        sub_line = f"☀️ 早晨簡報：{on}（每日 {sub['brief_time']}）"
    try:
        usage = db.get_usage_summary(user_id)
        usage_line = (
            f"🤖 Token 用量：今日 {usage['today_calls']} 次 ≈ ${usage['today_cost']:.4f}\n"
            f"　　　　　　 本月 {usage['month_calls']} 次 ≈ ${usage['month_cost']:.4f}"
        )
    except Exception as e:
        logger.warning(f"取得 token 用量失敗: {e}")
        usage_line = "🤖 Token 用量：（暫無資料）"
    try:
        today = _today()
        month_start = today.replace(day=1)
        es = db.expense_summarize(user_id, month_start, today)
        if es["count"] > 0:
            expense_line = f"💰 本月支出：NT${float(es['total_expense']):,.0f}（{es['count']} 筆）"
        else:
            expense_line = "💰 本月支出：尚無記錄"
    except Exception as e:
        logger.warning(f"取得月度支出失敗: {e}")
        expense_line = "💰 本月支出：（暫無資料）"
    return (
        "📊 Lumio 狀態\n"
        "━━━━━━━━━━━\n"
        f"{sub_line}\n"
        f"📝 待辦：{sum(1 for t in todos if not t[2])} 項未完成 / 共 {len(todos)}\n"
        f"📒 備忘：{len(notes)} 則\n"
        f"{expense_line}\n"
        f"{usage_line}"
    )


@handler.add(MessageEvent, message=TextMessageContent)
def on_text(event: MessageEvent):
    if _is_duplicate(event.message.id):
        logger.info(f"略過重送訊息 mid={event.message.id}")
        return
    started_at = time.monotonic()
    text = event.message.text
    user_id = event.source.user_id
    t = text.strip()

    # 自動註冊訂閱（任何訊息均觸發）
    db.upsert_subscription(user_id)

    if _rate_limited(user_id):
        _send(event.reply_token, user_id,
              "⚠️ 訊息頻率過高，請稍候片刻再試（每分鐘上限 15 則）", started_at)
        return

    # ── 快捷指令（直接執行，不走 Claude）
    if t in ("/reset", "/清除記憶"):
        _send(event.reply_token, user_id, handle_reset_memory(user_id), started_at)
    elif t == "/簡報":
        _send(event.reply_token, user_id, build_morning_briefing(user_id), started_at)
    elif t in ("/簡報 開", "/簡報開"):
        db.set_briefing(user_id, True)
        _send(event.reply_token, user_id, "✅ 早晨簡報已開啟（每日 08:00 推送）", started_at)
    elif t in ("/簡報 關", "/簡報關"):
        db.set_briefing(user_id, False)
        _send(event.reply_token, user_id, "🔕 早晨簡報已關閉", started_at)
    elif t in ("/狀態", "/status"):
        _send(event.reply_token, user_id, _build_status(user_id), started_at)
    elif t.startswith("/摘要 ") or t.startswith("/摘要\n"):
        url = t[3:].strip()
        _send(event.reply_token, user_id, summarize_url(url), started_at)
    elif t.startswith("/範本"):
        _send(event.reply_token, user_id, handle_template(t, user_id), started_at)
    elif t.startswith("/法規 ") or t.startswith("/法規\n"):
        q = t[3:].strip()
        _send(event.reply_token, user_id,
              law_search(q) if q else "📜 用法：/法規 <關鍵字或條號>", started_at)
    elif t.startswith("/旅遊"):
        _send(event.reply_token, user_id, handle_trip(t, user_id), started_at)
    elif t.startswith("/待辦") or t.startswith("/t"):
        _send(event.reply_token, user_id, _todo_response(t, user_id), started_at)
    elif t.startswith("/記事") or t.startswith("/備忘"):
        _send(event.reply_token, user_id, _note_response(t, user_id), started_at)
    elif t.startswith("/記帳"):
        _send(event.reply_token, user_id, _expense_response(t, user_id), started_at)
    elif t.startswith("/日曆") or t.startswith("/cal"):
        _send(event.reply_token, user_id, handle_cal(t), started_at)
    elif t in ("/h", "/help"):
        _send(event.reply_token, user_id, handle_help(), started_at)
    else:
        try:
            _send(event.reply_token, user_id, ask_claude(user_id, t), started_at)
        except Exception as e:
            logger.exception(f"Claude 呼叫錯誤: {e}")
            _send(event.reply_token, user_id, f"⚠️ 發生錯誤：{e}", started_at)


@handler.add(PostbackEvent)
def on_postback(event: PostbackEvent):
    """處理 Flex Message 按鈕點擊（待辦/記事互動操作）。"""
    started_at = time.monotonic()
    user_id = event.source.user_id
    db.upsert_subscription(user_id)

    data = parse_postback(event.postback.data or "")
    act = data.get("act", "")
    try:
        idx = int(data.get("i", "0"))
    except ValueError:
        idx = 0
    try:
        eid = int(data.get("id", "0"))
    except ValueError:
        eid = 0

    if act == "todo.done" and idx > 0:
        text_msg = todo_complete(user_id, idx)
        flex = todo_carousel(db.get_todos(user_id))
        _send(event.reply_token, user_id, flex if flex else text_msg, started_at)
    elif act == "todo.del" and idx > 0:
        text_msg = todo_delete(user_id, idx)
        flex = todo_carousel(db.get_todos(user_id))
        _send(event.reply_token, user_id, flex if flex else text_msg, started_at)
    elif act == "note.del" and idx > 0:
        text_msg = note_delete(user_id, idx)
        flex = note_carousel(db.get_notes(user_id))
        _send(event.reply_token, user_id, flex if flex else text_msg, started_at)
    elif act == "expense.del" and eid > 0:
        text_msg = expense_delete(user_id, eid)
        today = _today()
        flex = expense_carousel(
            db.list_expenses(user_id, today, today, limit=20),
            title=f"💰 今日（{today}）",
        )
        _send(event.reply_token, user_id, flex if flex else text_msg, started_at)
    else:
        logger.warning(f"未知 postback act={act} data={event.postback.data!r}")
        _send(event.reply_token, user_id, "⚠️ 操作未識別，請重試", started_at)


@handler.add(MessageEvent, message=ImageMessageContent)
def on_image(event: MessageEvent):
    if _is_duplicate(event.message.id):
        logger.info(f"略過重送圖片 mid={event.message.id}")
        return
    started_at = time.monotonic()
    user_id = event.source.user_id
    db.upsert_subscription(user_id)
    if _rate_limited(user_id):
        _send(event.reply_token, user_id,
              "⚠️ 訊息頻率過高，請稍候片刻再試", started_at)
        return
    try:
        raw = line_bot_blob.get_message_content(event.message.id)
        image_b64 = base64.b64encode(raw).decode("utf-8")
        _send(event.reply_token, user_id, ask_claude(user_id, "", image_b64), started_at)
    except Exception as e:
        logger.exception(f"圖片分析錯誤: {e}")
        _send(event.reply_token, user_id, f"⚠️ 圖片分析失敗：{e}", started_at)


@handler.add(MessageEvent, message=AudioMessageContent)
def on_audio(event: MessageEvent):
    """語音訊息：Whisper 轉文字 → 餵給 Claude 主迴圈，回覆同對話路徑。"""
    if _is_duplicate(event.message.id):
        logger.info(f"略過重送語音 mid={event.message.id}")
        return
    started_at = time.monotonic()
    user_id = event.source.user_id
    db.upsert_subscription(user_id)
    if _rate_limited(user_id):
        _send(event.reply_token, user_id,
              "⚠️ 訊息頻率過高，請稍候片刻再試", started_at)
        return
    try:
        raw = bytes(line_bot_blob.get_message_content(event.message.id))
        text = transcribe(raw)
        if text is None:
            _send(event.reply_token, user_id,
                  "⚠️ 尚未設定語音轉文字（需設定 OPENAI_API_KEY 環境變數）", started_at)
            return
        if not text.strip():
            _send(event.reply_token, user_id,
                  "⚠️ 語音內容為空或無法辨識，請再試一次", started_at)
            return
        logger.info(f"Whisper 轉錄 user={user_id} chars={len(text)}")
        # 將辨識結果送入 Claude，回覆前綴提示「你說：」讓老闆確認辨識正確
        reply = ask_claude(user_id, text)
        _send(event.reply_token, user_id, f"🎤 你說：「{text}」\n\n{reply}", started_at)
    except Exception as e:
        logger.exception(f"語音處理錯誤: {e}")
        _send(event.reply_token, user_id, f"⚠️ 語音處理失敗：{e}", started_at)


@handler.add(MessageEvent, message=FileMessageContent)
def on_file(event: MessageEvent):
    if _is_duplicate(event.message.id):
        logger.info(f"略過重送檔案 mid={event.message.id}")
        return
    started_at = time.monotonic()
    user_id = event.source.user_id
    db.upsert_subscription(user_id)
    if _rate_limited(user_id):
        _send(event.reply_token, user_id,
              "⚠️ 訊息頻率過高，請稍候片刻再試", started_at)
        return

    filename = event.message.file_name or "document"
    file_size = event.message.file_size or 0

    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    supported = ("pdf", "txt", "md", "csv", "docx", "pptx")
    if ext not in supported:
        _send(event.reply_token, user_id,
              f"⚠️ 目前支援 PDF、TXT、MD、CSV、DOCX、PPTX 格式\n收到的是：{filename}", started_at)
        return

    if file_size > 20 * 1024 * 1024:
        _send(event.reply_token, user_id,
              f"⚠️ 檔案太大({file_size/1024/1024:.1f}MB),請上傳 20MB 以下的文件", started_at)
        return

    try:
        raw = bytes(line_bot_blob.get_message_content(event.message.id))
        if ext in ("docx", "pptx"):
            _send(event.reply_token, user_id, analyze_meeting_file(user_id, raw, filename), started_at)
        else:
            _send(event.reply_token, user_id, analyze_file(user_id, raw, filename), started_at)
    except Exception as e:
        logger.exception(f"文件分析錯誤: {e}")
        _send(event.reply_token, user_id, f"⚠️ 文件分析失敗：{e}", started_at)
