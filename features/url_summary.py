"""網址摘要：用 Perplexity sonar 直接讀取並摘要 URL"""
import os
import logging
import requests

logger = logging.getLogger("lumio.url_summary")


_PROMPT = (
    "請用繁體中文摘要以下網址的內容：{url}\n\n"
    "格式（純文字 + emoji，禁用 Markdown）：\n"
    "①一句話總結\n"
    "②主要重點（條列 3 ~ 5 點）\n"
    "③值得關注或後續行動（如有）"
)


def summarize_url(url: str) -> str:
    api_key = os.getenv("PERPLEXITY_API_KEY", "")
    if not api_key:
        return "⚠️ 摘要功能未設定（缺 PERPLEXITY_API_KEY）"

    try:
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "sonar",
                "messages": [
                    {"role": "system", "content": "你是專業內容摘要員，繁體中文，先結論再細節，禁用 Markdown。"},
                    {"role": "user", "content": _PROMPT.format(url=url)},
                ],
            },
            timeout=45,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data["choices"][0]["message"]["content"]
        return f"📰 網址摘要\n{url}\n\n{answer}"
    except Exception as e:
        logger.warning(f"URL 摘要失敗 {url}: {e}")
        return f"⚠️ 摘要失敗：{e}"
