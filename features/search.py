"""網路搜尋（Perplexity）+ Google Maps"""
from urllib.parse import quote

from features.perplexity import chat as pplx_chat


_SEARCH_SYS = (
    "你是專業資訊研究員，從多個來源交叉比對彙整最新資訊。"
    "引用多個不同來源，標註來源編號 [1][2]...，繁體中文，先結論再細節。"
)


def web_search(query: str) -> str:
    r = pplx_chat(_SEARCH_SYS, query, recency="month")
    if r["error"]:
        return f"搜尋時發生錯誤：{r['error']}"
    answer = r["answer"]
    if r["citations"]:
        sources = "\n".join(f"[{i+1}] {url}" for i, url in enumerate(r["citations"][:8]))
        answer = f"{answer}\n\n📎 參考來源：\n{sources}"
    return answer


def google_map_search(places: list[dict]) -> str:
    out = []
    for place in places:
        name = place["name"]
        desc = place.get("description", "")
        url = f"https://maps.google.com/maps?q={quote(name)}"
        line = f"📍 {name}" + (f" — {desc}" if desc else "")
        out.append(f"{line}\n{url}")
    return "\n\n".join(out)
