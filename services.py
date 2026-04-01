"""外部服務封裝：搜尋、地圖、天氣"""
import os
import requests
from urllib.parse import quote


def _refine_query(raw_query: str) -> str:
    """用 Claude 將模糊/不精確的搜尋詞優化為精準搜尋語句"""
    from config import anthropic_client, CLAUDE_MODEL
    try:
        resp = anthropic_client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=100,
            system=(
                "你是搜尋查詢優化器。用戶輸入可能不精確、有錯字、口語化或太模糊。"
                "你的任務是將其轉換為精準的搜尋語句，以獲得最佳搜尋結果。\n"
                "規則：\n"
                "1. 修正明顯的錯字和別字（例：「台積店」→「台積電」）\n"
                "2. 口語化表達轉為搜尋關鍵字（例：「那個很紅的AI公司」→「OpenAI 公司 最新動態」）\n"
                "3. 補充必要的上下文（例：「鴻海股價」→「鴻海 2330 今日股價」）\n"
                "4. 如果已經夠精確，原樣回傳即可\n"
                "5. 只回傳優化後的搜尋語句，不要加任何解釋"
            ),
            messages=[{"role": "user", "content": raw_query}],
        )
        refined = resp.content[0].text.strip()
        if refined:
            return refined
    except Exception:
        pass
    return raw_query


def web_search(query: str) -> str:
    """用 Perplexity API 搜尋（自動優化模糊查詢）"""
    api_key = os.getenv("PERPLEXITY_API_KEY", "")
    if not api_key:
        return "搜尋功能未設定，請在環境變數加入 PERPLEXITY_API_KEY。"

    refined_query = _refine_query(query)

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
                    {"role": "user", "content": refined_query},
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
        "特定公司/產品/人物的近況、或任何你不確定的事實性問題時，使用這個工具。\n"
        "重要：老闆輸入可能口語化、有錯字或不精確。你必須先理解老闆的真正意圖，"
        "再將 query 轉換為精準的搜尋關鍵字。例如：\n"
        "- 老闆說「那個AI股票」→ query 用「NVIDIA 輝達 股價 最新」\n"
        "- 老闆說「台積店」→ 理解為「台積電」→ query 用「台積電 TSMC 最新消息」\n"
        "- 老闆說「最近很紅的那個減肥藥」→ query 用「GLP-1 減肥藥 Ozempic Wegovy 最新」\n"
        "永遠用完整、精確的關鍵字搜尋，不要直接照搬老闆的原話。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "優化後的精準搜尋關鍵字（修正錯字、補充上下文、去口語化）",
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
