"""台灣法規查詢（用 Perplexity，回正文為主）"""
from features.perplexity import chat as pplx_chat


_SYS = (
    "你是台灣法規研究員。優先參考全國法規資料庫（law.moj.gov.tw）。"
    "回傳法規正文，繁體中文，純文字，禁用 Markdown，禁加個人解讀。"
)
_PROMPT = (
    "請查詢台灣以下法規條文，並以正文為主回傳：{query}\n\n"
    "格式（純文字，禁用 Markdown）：\n"
    "📜 法規名稱：（完整法規名稱、最後修法日期）\n\n"
    "📖 條文正文：\n"
    "（逐條完整列出條文文字；若查詢為單一條文，僅列該條；多條時以條號編排）\n\n"
    "若查詢結果不明確，列出可能相符的法規供使用者選擇。"
)


def law_search(query: str) -> str:
    r = pplx_chat(_SYS, _PROMPT.format(query=query), recency="year")
    if r["error"]:
        return f"⚠️ 法規查詢失敗：{r['error']}"
    out = f"📜 法規查詢：{query}\n\n{r['answer']}"
    if r["citations"]:
        sources = "\n".join(f"[{i+1}] {url}" for i, url in enumerate(r["citations"][:5]))
        out += f"\n\n📎 來源：\n{sources}"
    return out
