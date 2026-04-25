"""Perplexity sonar API 共用呼叫層"""
import os
import logging
import requests

logger = logging.getLogger("lumio.perplexity")

_ENDPOINT = "https://api.perplexity.ai/chat/completions"


def chat(system: str, user: str, recency: str | None = None, timeout: int = 45) -> dict:
    """呼叫 Perplexity sonar。回傳 {"answer", "citations", "error"}。
    error 為 None 表示成功；否則 answer 為 ""。"""
    api_key = os.getenv("PERPLEXITY_API_KEY", "")
    if not api_key:
        return {"answer": "", "citations": [], "error": "PERPLEXITY_API_KEY 未設定"}

    body: dict = {
        "model": "sonar",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if recency:
        body["search_recency_filter"] = recency

    try:
        resp = requests.post(
            _ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
            timeout=timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return {
            "answer": data["choices"][0]["message"]["content"],
            "citations": data.get("citations", []),
            "error": None,
        }
    except Exception as e:
        logger.warning(f"Perplexity 呼叫失敗: {e}")
        return {"answer": "", "citations": [], "error": str(e)}
