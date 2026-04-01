"""外部服務封裝：搜尋、地圖、天氣"""
import os
import requests
from urllib.parse import quote


def web_search(query: str) -> str:
    """用 Perplexity API 搜尋"""
    api_key = os.getenv("PERPLEXITY_API_KEY", "")
    if not api_key:
        return "搜尋功能未設定，請在環境變數加入 PERPLEXITY_API_KEY。"
    try:
        resp = requests.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "sonar",
                "messages": [
                    {"role": "system", "content": "請用繁體中文回答，提供最新、準確的資訊。附上資料來源。"},
                    {"role": "user", "content": query},
                ],
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        answer = data["choices"][0]["message"]["content"]
        citations = data.get("citations", [])
        if citations:
            sources = "\n".join(f"[{i+1}] {url}" for i, url in enumerate(citations[:3]))
            return f"{answer}\n\n📎 參考來源：\n{sources}"
        return answer
    except Exception as e:
        return f"搜尋時發生錯誤：{e}"


def google_map_search(places: list[dict]) -> str:
    """產生 Google Maps 連結"""
    results = []
    for place in places:
        name = place["name"]
        desc = place.get("description", "")
        map_url = f"https://maps.google.com/maps?q={quote(name)}"
        line = f"📍 {name}"
        if desc:
            line += f" — {desc}"
        line += f"\n{map_url}"
        results.append(line)
    return "\n\n".join(results)


def get_weather(city: str = "Taipei") -> str:
    """查詢天氣"""
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


# ─── Claude Tool 定義 ───
WEB_SEARCH_TOOL = {
    "name": "web_search",
    "description": (
        "搜尋網路上的即時資訊。當老闆問到最新新聞、即時資訊、股價、"
        "特定公司/產品/人物的近況、或任何你不確定的事實性問題時，使用這個工具。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "搜尋關鍵字（建議用英文或中文皆可）",
            }
        },
        "required": ["query"],
    },
}

GOOGLE_MAP_TOOL = {
    "name": "google_map_search",
    "description": (
        "查詢地點並產生 Google Maps 連結。當對話中提到具體地點、景點、餐廳、"
        "美食、飯店、會議地點、公司地址等，使用這個工具提供地圖連結，"
        "讓老闆可以直接點開導航。可以一次查詢多個地點。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "places": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "地點名稱（盡量具體，例如「博多一幸舍 福岡總本店」而非「拉麵店」）",
                        },
                        "description": {
                            "type": "string",
                            "description": "簡短描述這個地點（例如「濃厚豚骨拉麵名店」）",
                        },
                    },
                    "required": ["name"],
                },
                "description": "要查詢的地點列表",
            }
        },
        "required": ["places"],
    },
}

TOOLS = [WEB_SEARCH_TOOL, GOOGLE_MAP_TOOL]


def dispatch_tool(name: str, input_data: dict) -> str:
    """統一分派 tool call"""
    if name == "web_search":
        return web_search(input_data["query"])
    if name == "google_map_search":
        return google_map_search(input_data["places"])
    return "未知的工具"
