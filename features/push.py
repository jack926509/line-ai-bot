"""LINE Push API 封裝（含失敗 logger，無重試 — 由 push_log 防重）"""
import logging
from linebot.v3.messaging import PushMessageRequest, TextMessage
from config import line_bot_api

logger = logging.getLogger("lumio.push")


def push_text(user_id: str, text: str) -> bool:
    """主動推送文字訊息至指定 LINE userId。回傳是否成功。"""
    if not user_id:
        logger.warning("push_text 缺 user_id")
        return False
    try:
        line_bot_api.push_message(
            PushMessageRequest(to=user_id, messages=[TextMessage(text=text)])
        )
        return True
    except Exception as e:
        logger.warning(f"push 失敗 user={user_id}: {e}")
        return False
