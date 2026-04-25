"""環境變數與共用初始化"""
import os
import logging
from dotenv import load_dotenv
from anthropic import Anthropic
from linebot.v3 import WebhookHandler
from linebot.v3.messaging import ApiClient, Configuration, MessagingApi, MessagingApiBlob

load_dotenv()

# ─── Logging ───
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("lumio")

# ─── 環境變數 ───
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_CHANNEL_ACCESS_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

# ─── 共用常數 ───
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MODEL_LIGHT = "claude-haiku-4-5-20251001"
TZ_NAME = "Asia/Taipei"
WEEKDAY_NAMES = ["週一", "週二", "週三", "週四", "週五", "週六", "週日"]

# ─── 共用實例 ───
line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
webhook_handler = WebhookHandler(LINE_CHANNEL_SECRET)
anthropic_client = Anthropic(api_key=ANTHROPIC_API_KEY)

# ApiClient 全域單例（urllib3 連線池 thread-safe，避免每訊息重建）
api_client = ApiClient(line_config)
line_bot_api = MessagingApi(api_client)
line_bot_blob = MessagingApiBlob(api_client)

# Bot userId（啟動後由 lifespan 設定）
BOT_USER_ID = ""
