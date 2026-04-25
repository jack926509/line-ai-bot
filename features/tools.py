"""所有 Claude tool 定義 + dispatch（含 user_id 支援）"""
from features.search import web_search, google_map_search
from features.calendar import (
    get_events, get_upcoming_events, add_event,
    update_event, delete_event, check_free_busy,
)
from features.url_summary import summarize_url
from features.doc_official import (
    gen_official_doc,
    template_add, template_list, template_apply, template_delete,
)
from features.law import law_search
from features.trip import trip_create, trip_list, trip_detail, trip_delete
from features.workflow import compose_workflow
import features.todo as todo_feat
import features.note as note_feat


# ── Tool 定義 ────────────────────────────────────


_WEB_SEARCH = {
    "name": "web_search",
    "description": (
        "搜尋網路即時資訊。老闆問新聞、股價、天氣、公司動態、任何不確定的事實時使用。"
        "自動優化模糊/口語/錯字查詢為精準關鍵字。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "優化後的精準搜尋關鍵字"},
        },
        "required": ["query"],
    },
}

_SUMMARIZE_URL = {
    "name": "summarize_url",
    "description": (
        "摘要網址內容。老闆貼網址、新聞連結、想了解某個 URL 內容時主動使用。"
        "回傳一句話總結 + 主要重點 + 後續行動建議。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "完整網址（http:// 或 https://）"},
        },
        "required": ["url"],
    },
}

_GOOGLE_MAP = {
    "name": "google_map_search",
    "description": (
        "查詢地點並產生 Google Maps 連結。對話中提到餐廳、景點、地址、"
        "會議地點等時，主動提供地圖連結讓老闆導航。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "places": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "地點名稱（盡量具體）"},
                        "description": {"type": "string", "description": "簡短描述"},
                    },
                    "required": ["name"],
                },
                "description": "要查詢的地點列表",
            }
        },
        "required": ["places"],
    },
}

_GCAL_QUERY = {
    "name": "gcal_query",
    "description": "查詢 Google Calendar 行程。老闆問「今天有什麼行程」「明天有會嗎」「這週行程」時使用。",
    "input_schema": {
        "type": "object",
        "properties": {
            "date": {"type": "string", "description": "查詢日期 YYYY-MM-DD，不填查今天"},
            "days": {"type": "integer", "description": "查幾天（預設 1）", "default": 1},
        },
        "required": [],
    },
}

_GCAL_UPCOMING = {
    "name": "gcal_upcoming",
    "description": "查詢從現在起最近 N 筆行程。老闆問「接下來有什麼安排」「即將到來的行程」時使用。",
    "input_schema": {
        "type": "object",
        "properties": {
            "count": {"type": "integer", "description": "筆數（預設 5，最多 10）", "default": 5},
        },
        "required": [],
    },
}

_GCAL_ADD = {
    "name": "gcal_add",
    "description": (
        "新增 Google Calendar 行程。老闆說「幫我排明天3點開會」「記一下週五整天出差」時使用。"
        "時間用 ISO 格式（2025-04-22T15:00:00），整天行程只填日期。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "行程標題"},
            "start_time": {"type": "string", "description": "開始時間（ISO 或 YYYY-MM-DD）"},
            "end_time": {"type": "string", "description": "結束時間（選填，預設 1 小時後）"},
            "location": {"type": "string", "description": "地點（選填）"},
            "description": {"type": "string", "description": "備註（選填）"},
        },
        "required": ["title", "start_time"],
    },
}

_GCAL_UPDATE = {
    "name": "gcal_update",
    "description": (
        "修改現有行程（標題/時間/地點/備註）。老闆說「把週五的會議改到下午5點」"
        "「把聚餐地點改成信義區」時使用。可以只改部分欄位。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "要修改的行程標題關鍵字"},
            "date": {"type": "string", "description": "原行程日期 YYYY-MM-DD（選填）"},
            "new_title": {"type": "string", "description": "新標題（選填）"},
            "new_start": {"type": "string", "description": "新開始時間 ISO（選填）"},
            "new_end": {"type": "string", "description": "新結束時間 ISO（選填）"},
            "new_location": {"type": "string", "description": "新地點（選填）"},
            "new_description": {"type": "string", "description": "新備註（選填）"},
        },
        "required": ["title"],
    },
}

_GCAL_DELETE = {
    "name": "gcal_delete",
    "description": "刪除 Google Calendar 行程。老闆說「取消明天的會議」「把聚餐刪掉」時使用。",
    "input_schema": {
        "type": "object",
        "properties": {
            "title": {"type": "string", "description": "要刪除的行程標題關鍵字"},
            "date": {"type": "string", "description": "行程日期 YYYY-MM-DD（選填）"},
        },
        "required": ["title"],
    },
}

_GCAL_FREE_BUSY = {
    "name": "gcal_free_busy",
    "description": "查詢某時段是否有空。老闆問「明天下午3點有空嗎」「週五2點到4點有衝突嗎」時使用。",
    "input_schema": {
        "type": "object",
        "properties": {
            "start_time": {"type": "string", "description": "查詢開始時間 ISO"},
            "end_time": {"type": "string", "description": "查詢結束時間 ISO"},
        },
        "required": ["start_time", "end_time"],
    },
}

_TODO_LIST = {
    "name": "todo_list",
    "description": "查看老闆的待辦清單。老闆問「我有什麼待辦」「今天要做什麼」時使用。",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

_TODO_ADD = {
    "name": "todo_add",
    "description": (
        "新增待辦事項。老闆說「幫我記下要買牛奶」「待辦加一個準備報告」時使用。"
        "可以指定分類（工作/私人）和到期日。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "待辦事項內容"},
            "category": {"type": "string", "description": "分類（選填，例如「工作」「私人」）"},
            "due_date": {"type": "string", "description": "到期日 YYYY-MM-DD（選填）"},
        },
        "required": ["content"],
    },
}

_TODO_COMPLETE = {
    "name": "todo_complete",
    "description": (
        "勾選完成待辦事項。老闆說「第2項完成了」「買牛奶做完了」時使用。"
        "若不知道編號，先用 todo_list 查看再操作。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "待辦事項編號（從 1 開始）"},
        },
        "required": ["index"],
    },
}

_TODO_DELETE = {
    "name": "todo_delete",
    "description": "刪除待辦事項。老闆說「刪掉第3項」「不用記了，刪掉那個」時使用。",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "待辦事項編號（從 1 開始）"},
        },
        "required": ["index"],
    },
}

_NOTE_LIST = {
    "name": "note_list",
    "description": "查看備忘錄。老闆問「我記了什麼」「備忘有哪些」時使用。",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

_NOTE_ADD = {
    "name": "note_add",
    "description": "新增備忘錄。老闆說「記下客戶說預算500萬」「備忘：明天帶合約」時使用。",
    "input_schema": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "備忘內容"},
        },
        "required": ["content"],
    },
}

_NOTE_DELETE = {
    "name": "note_delete",
    "description": "刪除備忘錄。老闆說「刪掉第2則備忘」時使用。",
    "input_schema": {
        "type": "object",
        "properties": {
            "index": {"type": "integer", "description": "備忘編號（從 1 開始）"},
        },
        "required": ["index"],
    },
}


_GEN_OFFICIAL_DOC = {
    "name": "gen_official_doc",
    "description": (
        "生成台灣政府公文體初稿（受文者 / 主旨 / 說明 / 擬辦 / 陳 / 核 結構）。"
        "老闆說「幫我擬一份公文回環境部」「寫一份簽呈，主旨是⋯」時使用。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "recipient": {"type": "string", "description": "受文者（機關名稱）"},
            "subject":   {"type": "string", "description": "主旨"},
            "points":    {"type": "array", "items": {"type": "string"},
                          "description": "說明事項重點（條列；若無可省略）"},
            "basis":     {"type": "string", "description": "依據（選填）"},
            "plan":      {"type": "string", "description": "擬辦方向（選填）"},
        },
        "required": ["recipient", "subject"],
    },
}

_TEMPLATE_LIST = {
    "name": "template_list",
    "description": "查看公文範本庫。老闆問「我有哪些範本」時使用。",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

_TEMPLATE_ADD = {
    "name": "template_add",
    "description": (
        "新增公文範本到範本庫。老闆說「幫我把這個存成範本」「新增範本：裁處答辯，"
        "正文⋯」時使用。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name":     {"type": "string", "description": "範本名稱"},
            "category": {"type": "string", "description": "分類（裁處 / 答辯 / 改善 / 會議回覆 等）"},
            "body":     {"type": "string", "description": "範本正文"},
        },
        "required": ["name", "body"],
    },
}

_TEMPLATE_APPLY = {
    "name": "template_apply",
    "description": "取用範本：依編號回傳第 N 則範本正文。老闆說「套用範本 2」「拿第 3 個範本」時使用。",
    "input_schema": {
        "type": "object",
        "properties": {"index": {"type": "integer", "description": "範本編號（從 1 開始）"}},
        "required": ["index"],
    },
}

_TEMPLATE_DELETE = {
    "name": "template_delete",
    "description": "刪除指定編號的範本。",
    "input_schema": {
        "type": "object",
        "properties": {"index": {"type": "integer", "description": "範本編號（從 1 開始）"}},
        "required": ["index"],
    },
}

_LAW_SEARCH = {
    "name": "law_search",
    "description": (
        "查詢台灣法規條文正文。老闆問「空污法第 24 條」「水污法施行細則」"
        "「廢棄物清理法」等法規條文時使用。優先回正文。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "法規名稱與條號（盡量具體，如「空污法第24條」）"}},
        "required": ["query"],
    },
}

_TRIP_CREATE = {
    "name": "trip_create",
    "description": (
        "建立旅遊行程容器並自動將每個地點寫入 Google Calendar。"
        "老闆說「規劃 7/15-19 福岡，第一天太宰府、糸島，第二天⋯」時使用。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "name":       {"type": "string", "description": "旅程名稱（例如「福岡 7/15-19」）"},
            "start_date": {"type": "string", "description": "開始日期 YYYY-MM-DD"},
            "end_date":   {"type": "string", "description": "結束日期 YYYY-MM-DD"},
            "places": {
                "type": "array",
                "description": "地點列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "day":      {"type": "integer", "description": "第幾天（1-based）"},
                        "time":     {"type": "string",  "description": "時間 HH:MM（可省略代表整天）"},
                        "name":     {"type": "string",  "description": "地點名稱"},
                        "location": {"type": "string",  "description": "完整地址（選填，預設用 name）"},
                        "note":     {"type": "string",  "description": "備註（選填）"},
                    },
                    "required": ["day", "name"],
                },
            },
        },
        "required": ["name", "start_date", "end_date", "places"],
    },
}

_TRIP_LIST = {
    "name": "trip_list",
    "description": "查看所有旅程。老闆問「我有哪些旅遊計畫」時使用。",
    "input_schema": {"type": "object", "properties": {}, "required": []},
}

_TRIP_DETAIL = {
    "name": "trip_detail",
    "description": "查看指定編號旅程的詳情（含每日地點）。",
    "input_schema": {
        "type": "object",
        "properties": {"index": {"type": "integer", "description": "旅程編號（從 1 開始）"}},
        "required": ["index"],
    },
}

_TRIP_DELETE = {
    "name": "trip_delete",
    "description": "刪除指定編號的旅程，並同步刪除 Google Calendar 上對應行程。",
    "input_schema": {
        "type": "object",
        "properties": {"index": {"type": "integer", "description": "旅程編號（從 1 開始）"}},
        "required": ["index"],
    },
}

_COMPOSE_WORKFLOW = {
    "name": "compose_workflow",
    "description": (
        "（預留功能，即將推出）多步驟工作流編排。老闆說「準備明天會議」"
        "「結束旅程整理」等需自動串聯多個工具的請求時使用。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {"goal": {"type": "string", "description": "工作流目標"}},
        "required": ["goal"],
    },
}


TOOLS = [
    _WEB_SEARCH, _SUMMARIZE_URL, _GOOGLE_MAP,
    _GCAL_QUERY, _GCAL_UPCOMING, _GCAL_ADD, _GCAL_UPDATE, _GCAL_DELETE, _GCAL_FREE_BUSY,
    _TODO_LIST, _TODO_ADD, _TODO_COMPLETE, _TODO_DELETE,
    _NOTE_LIST, _NOTE_ADD, _NOTE_DELETE,
    _GEN_OFFICIAL_DOC, _TEMPLATE_LIST, _TEMPLATE_ADD, _TEMPLATE_APPLY, _TEMPLATE_DELETE,
    _LAW_SEARCH,
    _TRIP_CREATE, _TRIP_LIST, _TRIP_DETAIL, _TRIP_DELETE,
    _COMPOSE_WORKFLOW,
]


# ── Dispatch ─────────────────────────────────────


def dispatch_tool(name: str, input_data: dict, user_id: str = "") -> str:
    d = input_data
    match name:
        # ── 搜尋 & 地圖
        case "web_search":
            return web_search(d["query"])
        case "summarize_url":
            return summarize_url(d["url"])
        case "google_map_search":
            return google_map_search(d["places"])

        # ── Google Calendar
        case "gcal_query":
            return get_events(date_str=d.get("date"), days=d.get("days", 1))
        case "gcal_upcoming":
            return get_upcoming_events(count=d.get("count", 5))
        case "gcal_add":
            return add_event(d["title"], d["start_time"], d.get("end_time"),
                             d.get("location"), d.get("description"))
        case "gcal_update":
            return update_event(d["title"], d.get("date"), d.get("new_title"),
                                d.get("new_start"), d.get("new_end"),
                                d.get("new_location"), d.get("new_description"))
        case "gcal_delete":
            return delete_event(d["title"], d.get("date"))
        case "gcal_free_busy":
            return check_free_busy(d["start_time"], d["end_time"])

        # ── 待辦
        case "todo_list":
            return todo_feat.todo_list(user_id)
        case "todo_add":
            return todo_feat.todo_add(user_id, d["content"],
                                      d.get("category", "一般"), d.get("due_date"))
        case "todo_complete":
            return todo_feat.todo_complete(user_id, d["index"])
        case "todo_delete":
            return todo_feat.todo_delete(user_id, d["index"])

        # ── 備忘
        case "note_list":
            return note_feat.note_list(user_id)
        case "note_add":
            return note_feat.note_add(user_id, d["content"])
        case "note_delete":
            return note_feat.note_delete(user_id, d["index"])

        # ── 公文 & 範本
        case "gen_official_doc":
            return gen_official_doc(
                d["recipient"], d["subject"],
                d.get("points"), d.get("basis"), d.get("plan"),
            )
        case "template_list":
            return template_list(user_id)
        case "template_add":
            return template_add(user_id, d["name"], d["body"], d.get("category", "一般"))
        case "template_apply":
            return template_apply(user_id, d["index"])
        case "template_delete":
            return template_delete(user_id, d["index"])

        # ── 法規
        case "law_search":
            return law_search(d["query"])

        # ── 旅遊
        case "trip_create":
            return trip_create(user_id, d["name"], d["start_date"], d["end_date"], d["places"])
        case "trip_list":
            return trip_list(user_id)
        case "trip_detail":
            return trip_detail(user_id, d["index"])
        case "trip_delete":
            return trip_delete(user_id, d["index"])

        # ── 工作流（預留）
        case "compose_workflow":
            return compose_workflow(d["goal"])

        case _:
            return "未知的工具"
