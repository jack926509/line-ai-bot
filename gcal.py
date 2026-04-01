"""Google Calendar API 封裝（免費 Service Account）"""
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
from config import TZ_NAME


def _get_service():
    """取得 Google Calendar API 服務"""
    creds_json = os.getenv("GOOGLE_CALENDAR_CREDENTIALS", "")
    if not creds_json:
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/calendar.readonly"]
        )
        return build("calendar", "v3", credentials=creds)
    except Exception as e:
        print(f"[Google Calendar] 初始化失敗：{e}")
        return None


def get_today_events() -> str:
    """取得今天的 Google Calendar 行程，回傳格式化字串"""
    service = _get_service()
    if not service:
        return ""
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID", "primary")
    try:
        now = datetime.now(ZoneInfo(TZ_NAME))
        start = now.replace(hour=0, minute=0, second=0).isoformat()
        end = now.replace(hour=23, minute=59, second=59).isoformat()
        result = service.events().list(
            calendarId=calendar_id,
            timeMin=start, timeMax=end,
            singleEvents=True, orderBy="startTime",
            timeZone=TZ_NAME,
        ).execute()
        events = result.get("items", [])
        if not events:
            return "📅 今天沒有行程安排"
        lines = ["📅 今日行程："]
        for ev in events:
            s = ev["start"].get("dateTime", ev["start"].get("date", ""))
            title = ev.get("summary", "（無標題）")
            location = ev.get("location", "")
            if "T" in s:
                time_str = datetime.fromisoformat(s).strftime("%H:%M")
                line = f"  ⏰ {time_str} {title}"
            else:
                line = f"  📌 整天 {title}"
            if location:
                line += f"\n     📍 {location}"
            lines.append(line)
        return "\n".join(lines)
    except Exception as e:
        print(f"[Google Calendar] 取得行程失敗：{e}")
        return ""
