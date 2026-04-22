"""環境變數與共用初始化"""
import os
from dotenv import load_dotenv
from anthropic import Anthropic
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import Configuration

load_dotenv()

# ─── 環境變數 ───
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ─── 共用常數 ───
CLAUDE_MODEL = "claude-sonnet-4-20250514"
CLAUDE_MODEL_LIGHT = "claude-haiku-4-5-20251001"
TZ_NAME = "Asia/Taipei"
WEEKDAY_NAMES = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]

# ─── 共用實例 ───
line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
webhook_handler = WebhookHandler(LINE_CHANNEL_SECRET)
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

# Bot userId（啟動後由 lifespan 設定）
BOT_USER_ID = ""
