"""Google Calendar API 封裝（Service Account，讀寫，快取 service）"""
import os
import json
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from config import TZ_NAME

_cached_service = None


def _get_service():
    global _cached_service
    if _cached_service is not None:
        return _cached_service
    creds_json = os.getenv("GOOGLE_CALENDAR_CREDENTIALS", "")
    if not creds_json:
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        info = json.loads(creds_json)
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/calendar"]
        )
        _cached_service = build("calendar", "v3", credentials=creds)
        return _cached_service
    except Exception as e:
        print(f"[Google Calendar] 初始化失敗：{e}")
        return None


def _cal_id() -> str:
    return os.getenv("GOOGLE_CALENDAR_ID", "primary")


_WEEKDAY = ["一", "二", "三", "四", "五", "六", "日"]


def get_events(date_str: str | None = None, days: int = 1) -> str:
    service = _get_service()
    if not service:
        return "⚠️ Google Calendar 未設定"
    try:
        if date_str:
            try:
                base = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=ZoneInfo(TZ_NAME))
            except ValueError:
                return "⚠️ 日期格式錯誤，請用 YYYY-MM-DD"
        else:
            base = datetime.now(ZoneInfo(TZ_NAME))

        start = base.replace(hour=0, minute=0, second=0).isoformat()
        end = (base + timedelta(days=days)).replace(hour=23, minute=59, second=59).isoformat()

        result = service.events().list(
            calendarId=_cal_id(),
            timeMin=start, timeMax=end,
            singleEvents=True, orderBy="startTime",
            timeZone=TZ_NAME,
        ).execute()
        events = result.get("items", [])
        if not events:
            label = base.strftime("%m/%d") if date_str else "今天"
            return f"📅 {label} 沒有行程安排"

        lines = []
        current_date = None
        for ev in events:
            s = ev["start"].get("dateTime", ev["start"].get("date", ""))
            title = ev.get("summary", "（無標題）")
            location = ev.get("location", "")

            if days > 1:
                ev_date = s[:10]
                if ev_date != current_date:
                    current_date = ev_date
                    d = datetime.strptime(ev_date, "%Y-%m-%d")
                    lines.append(f"\n📆 {d.month}/{d.day}（週{_WEEKDAY[d.weekday()]}）")

            if "T" in s:
                line = f"  ⏰ {datetime.fromisoformat(s).strftime('%H:%M')} {title}"
            else:
                line = f"  📌 整天 {title}"
            if location:
                line += f"\n     📍 {location}"
            lines.append(line)

        header = "📅 行程查詢結果：" if date_str else "📅 今日行程："
        return header + "\n".join(lines)
    except Exception as e:
        print(f"[Google Calendar] 查詢失敗：{e}")
        return f"⚠️ 行程查詢失敗：{e}"


def add_event(title: str, start_time: str, end_time: str | None = None,
              location: str | None = None, description: str | None = None) -> str:
    service = _get_service()
    if not service:
        return "⚠️ Google Calendar 未設定"
    try:
        is_all_day = len(start_time) == 10

        if is_all_day:
            event_body = {
                "summary": title,
                "start": {"date": start_time},
                "end": {"date": end_time or start_time},
            }
        else:
            if not start_time.endswith("+08:00") and "T" in start_time:
                start_time += "+08:00"
            if end_time:
                if not end_time.endswith("+08:00") and "T" in end_time:
                    end_time += "+08:00"
            else:
                end_time = (datetime.fromisoformat(start_time) + timedelta(hours=1)).isoformat()

            event_body = {
                "summary": title,
                "start": {"dateTime": start_time, "timeZone": TZ_NAME},
                "end": {"dateTime": end_time, "timeZone": TZ_NAME},
            }

        if location:
            event_body["location"] = location
        if description:
            event_body["description"] = description

        service.events().insert(calendarId=_cal_id(), body=event_body).execute()

        if is_all_day:
            time_info = f"📅 {start_time}"
        else:
            st = datetime.fromisoformat(start_time)
            et = datetime.fromisoformat(end_time)
            time_info = f"📅 {st.strftime('%m/%d')} ⏰ {st.strftime('%H:%M')}~{et.strftime('%H:%M')}"

        result = f"✅ 行程已新增！\n📌 {title}\n{time_info}"
        if location:
            result += f"\n📍 {location}"
        return result
    except Exception as e:
        print(f"[Google Calendar] 新增失敗：{e}")
        return f"⚠️ 行程新增失敗：{e}"


def delete_event(event_title: str, date_str: str | None = None) -> str:
    service = _get_service()
    if not service:
        return "⚠️ Google Calendar 未設定"
    try:
        now = datetime.now(ZoneInfo(TZ_NAME))
        if date_str:
            try:
                base = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=ZoneInfo(TZ_NAME))
            except ValueError:
                base = now
        else:
            base = now

        start = base.replace(hour=0, minute=0, second=0).isoformat()
        end = (base + timedelta(days=30)).isoformat()

        result = service.events().list(
            calendarId=_cal_id(),
            timeMin=start, timeMax=end,
            singleEvents=True, orderBy="startTime",
            q=event_title, timeZone=TZ_NAME,
        ).execute()
        events = result.get("items", [])
        if not events:
            return f"⚠️ 找不到標題包含「{event_title}」的行程"

        ev = events[0]
        service.events().delete(calendarId=_cal_id(), eventId=ev["id"]).execute()
        return f"🗑 已刪除行程：「{ev.get('summary', event_title)}」"
    except Exception as e:
        print(f"[Google Calendar] 刪除失敗：{e}")
        return f"⚠️ 行程刪除失敗：{e}"
