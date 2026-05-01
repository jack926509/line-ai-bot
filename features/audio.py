"""LINE 語音訊息 → Whisper 轉文字。

需設定 OPENAI_API_KEY 環境變數；未設定時 transcribe 會回 None 並由 handler 提示使用者。
"""
import io

from config import OPENAI_API_KEY

_client = None


def _get_client():
    """惰性建立 OpenAI client，避免無 key 時 import 失敗。"""
    global _client
    if not OPENAI_API_KEY:
        return None
    if _client is None:
        from openai import OpenAI
        _client = OpenAI(api_key=OPENAI_API_KEY)
    return _client


def transcribe(audio_bytes: bytes, filename: str = "voice.m4a") -> str | None:
    """將語音 bytes 轉為文字。回傳 None 代表無 API key。

    LINE 語音為 m4a 格式（AAC），Whisper 直接支援。
    """
    client = _get_client()
    if client is None:
        return None
    f = io.BytesIO(audio_bytes)
    f.name = filename  # OpenAI SDK 需要檔名以推測格式
    resp = client.audio.transcriptions.create(
        model="whisper-1",
        file=f,
    )
    return getattr(resp, "text", "") or ""
