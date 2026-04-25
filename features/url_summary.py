"""網址摘要（Perplexity sonar 直接讀取並摘要 URL）"""
from features.perplexity import chat as pplx_chat


_SYS = "你是專業內容摘要員，繁體中文，先結論再細節，禁用 Markdown。"
_PROMPT = (
    "請用繁體中文摘要以下網址的內容：{url}\n\n"
    "格式（純文字 + emoji，禁用 Markdown）：\n"
    "①一句話總結\n"
    "②主要重點（條列 3 ~ 5 點）\n"
    "③值得關注或後續行動（如有）"
)


def summarize_url(url: str) -> str:
    r = pplx_chat(_SYS, _PROMPT.format(url=url))
    if r["error"]:
        return f"⚠️ 摘要失敗：{r['error']}"
    return f"📰 網址摘要\n{url}\n\n{r['answer']}"
