"""所有 Claude tool 定義 + dispatch（含 user_id 支援）"""
from features.search import web_search, google_map_search
from features.calendar import (
    get_events, get_upcoming_events, add_event,
    update_event, delete_event, check_free_busy,
)
import features.todo as todo_feat


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


TOOLS = [
    _WEB_SEARCH, _GOOGLE_MAP,
    _GCAL_QUERY, _GCAL_UPCOMING, _GCAL_ADD, _GCAL_UPDATE, _GCAL_DELETE, _GCAL_FREE_BUSY,
    _TODO_LIST, _TODO_ADD, _TODO_COMPLETE, _TODO_DELETE,
    _NOTE_LIST, _NOTE_ADD, _NOTE_DELETE,
]


# ── Dispatch ─────────────────────────────────────


def dispatch_tool(name: str, input_data: dict, user_id: str = "") -> str:
    d = input_data
    match name:
        # ── 搜尋 & 地圖
        case "web_search":
            return web_search(d["query"])
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
            return todo_feat.note_list(user_id)
        case "note_add":
            return todo_feat.note_add(user_id, d["content"])
        case "note_delete":
            return todo_feat.note_delete(user_id, d["index"])

        case _:
            return "未知的工具"
