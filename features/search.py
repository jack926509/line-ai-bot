"""網路搜尋、Google Maps、天氣"""
import os
import requests
from urllib.parse import quote


def web_search(query: str) -> str:
    """用 Perplexity 搜尋。query 由 Claude 傳入，已是最佳化關鍵字，直接使用。"""
    api_key = os.getenv("PERPLEXITY_API_KEY", "")
    if not api_key:
        return "搜尋功能未設定，請加入 PERPLEXITY_API_KEY。"
    try:
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": "sonar",
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "你是專業資訊研究員，從多個來源交叉比對彙整最新資訊。"
                            "引用多個不同來源，標註來源編號 [1][2]...，繁體中文，先結論再細節。"
                        ),
                    },
                    {"role": "user", "content": query},
                ],
                "search_recency_filter": "month",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data["choices"][0]["message"]["content"]
        citations = data.get("citations", [])
        if citations:
            sources = "\n".join(f"[{i+1}] {url}" for i, url in enumerate(citations[:8]))
            return f"{answer}\n\n📎 參考來源：\n{sources}"
        return answer
    except Exception as e:
        return f"搜尋時發生錯誤：{e}"


def google_map_search(places: list[dict]) -> str:
    results = []
    for place in places:
        name = place["name"]
        desc = place.get("description", "")
        url = f"https://maps.google.com/maps?q={quote(name)}"
        line = f"📍 {name}"
        if desc:
            line += f" — {desc}"
        line += f"\n{url}"
        results.append(line)
    return "\n\n".join(results)


def get_weather(city: str = "Taipei") -> str:
    try:
        resp = requests.get(
            f"https://wttr.in/{city}?format=%l:+%c+%t&lang=zh",
            headers={"Accept-Charset": "utf-8"},
            timeout=5,
        )
        resp.encoding = "utf-8"
        return resp.text.strip()
    except Exception:
        return ""
