"""網址摘要：HTML → Perplexity；PDF → 下載 + pypdf 抽文 + Claude 摘要。"""
import logging
from urllib.parse import urlparse

import requests

from features.perplexity import chat as pplx_chat

logger = logging.getLogger("lumio.url_summary")


_SYS = "你是專業內容摘要員，繁體中文，先結論再細節，禁用 Markdown。"
_PROMPT = (
    "請用繁體中文摘要以下網址的內容：{url}\n\n"
    "格式（純文字 + emoji，禁用 Markdown）：\n"
    "①一句話總結\n"
    "②主要重點（條列 3 ~ 5 點）\n"
    "③值得關注或後續行動（如有）"
)

_PDF_DOWNLOAD_MAX = 20 * 1024 * 1024  # 與 chat.py FILE_SIZE_MAX 對齊
_PDF_DOWNLOAD_TIMEOUT = 30


def _is_pdf_url(url: str) -> bool:
    return urlparse(url).path.lower().endswith(".pdf")


def _download_pdf(url: str) -> bytes | str:
    """下載 PDF；成功回 bytes，失敗回錯誤訊息字串。"""
    try:
        resp = requests.get(
            url, timeout=_PDF_DOWNLOAD_TIMEOUT, stream=True,
            headers={"User-Agent": "Mozilla/5.0 (Lumio)"},
        )
        resp.raise_for_status()
    except Exception as e:
        logger.warning(f"PDF 下載失敗 url={url}: {e}")
        return f"⚠️ PDF 下載失敗：{e}"

    chunks: list[bytes] = []
    total = 0
    for chunk in resp.iter_content(chunk_size=64 * 1024):
        if not chunk:
            continue
        total += len(chunk)
        if total > _PDF_DOWNLOAD_MAX:
            return f"⚠️ PDF 太大（>{_PDF_DOWNLOAD_MAX // 1024 // 1024}MB），請改用上傳檔案"
        chunks.append(chunk)
    return b"".join(chunks)


def summarize_url(url: str, user_id: str = "") -> str:
    if _is_pdf_url(url):
        result = _download_pdf(url)
        if isinstance(result, str):
            return result
        # 延遲 import 避免 features.tools ↔ features.chat 循環依賴
        from features.chat import analyze_pdf_bytes
        filename = urlparse(url).path.rsplit("/", 1)[-1] or "remote.pdf"
        body = analyze_pdf_bytes(result, filename, user_id=user_id)
        return f"📄 PDF 摘要\n{url}\n\n{body}"

    r = pplx_chat(_SYS, _PROMPT.format(url=url))
    if r["error"]:
        return f"⚠️ 摘要失敗：{r['error']}"
    return f"📰 網址摘要\n{url}\n\n{r['answer']}"
