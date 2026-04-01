"""環境變數與共用初始化"""
import os
from dotenv import load_dotenv
from anthropic import Anthropic
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

# ─── 環境變數 ───
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
GROUP_ID = os.getenv("LINE_GROUP_ID", "")

# ─── 共用常數 ───
CLAUDE_MODEL = "claude-sonnet-4-20250514"
TZ_NAME = "Asia/Taipei"
WEEKDAY_NAMES = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]

# ─── 共用實例 ───
line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
webhook_handler = WebhookHandler(LINE_CHANNEL_SECRET)
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)
scheduler = AsyncIOScheduler(timezone=TZ_NAME)

# Bot 自己的 userId（啟動後由 lifespan 設定）
BOT_USER_ID = ""


def get_line_api():
    """取得 LINE Messaging API client（context manager）"""
    from linebot.v3.messaging import ApiClient
    return ApiClient(line_config)
