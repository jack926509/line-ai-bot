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


def _fmt_event_line(ev: dict, show_date: bool = False) -> str:
    s = ev["start"].get("dateTime", ev["start"].get("date", ""))
    title = ev.get("summary", "（無標題）")
    location = ev.get("location", "")
    description = ev.get("description", "")

    if "T" in s:
        time_part = datetime.fromisoformat(s).strftime("%H:%M")
        line = f"  ⏰ {time_part} {title}"
    else:
        line = f"  📌 整天 {title}"

    if show_date:
        d = datetime.strptime(s[:10], "%Y-%m-%d")
        line = f"  {d.month}/{d.day}（週{_WEEKDAY[d.weekday()]}）{line.strip()}"

    if location:
        line += f"\n     📍 {location}"
    if description and len(description) <= 40:
        line += f"\n     📝 {description}"
    return line


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
        # 修正：days=1 只查當天，end 為當天 23:59:59
        end = (base + timedelta(days=days - 1)).replace(hour=23, minute=59, second=59).isoformat()

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

            if days > 1:
                ev_date = s[:10]
                if ev_date != current_date:
                    current_date = ev_date
                    d = datetime.strptime(ev_date, "%Y-%m-%d")
                    lines.append(f"\n📆 {d.month}/{d.day}（週{_WEEKDAY[d.weekday()]}）")

            lines.append(_fmt_event_line(ev))

        header = "📅 行程查詢結果：" if date_str else "📅 今日行程："
        return header + "\n".join(lines)
    except Exception as e:
        print(f"[Google Calendar] 查詢失敗：{e}")
        return f"⚠️ 行程查詢失敗：{e}"


def get_upcoming_events(count: int = 5) -> str:
    """取得從現在起算最近 N 筆行程"""
    service = _get_service()
    if not service:
        return "⚠️ Google Calendar 未設定"
    try:
        now = datetime.now(ZoneInfo(TZ_NAME))
        result = service.events().list(
            calendarId=_cal_id(),
            timeMin=now.isoformat(),
            maxResults=min(count, 10),
            singleEvents=True,
            orderBy="startTime",
            timeZone=TZ_NAME,
        ).execute()
        events = result.get("items", [])
        if not events:
            return "📅 近期沒有任何行程安排"

        lines = [f"📅 即將到來的 {len(events)} 筆行程："]
        current_date = None
        today = now.date()
        for ev in events:
            s = ev["start"].get("dateTime", ev["start"].get("date", ""))
            ev_date = s[:10]
            if ev_date != current_date:
                current_date = ev_date
                d = datetime.strptime(ev_date, "%Y-%m-%d")
                diff = (d.date() - today).days
                if diff == 0:
                    day_label = "今天"
                elif diff == 1:
                    day_label = "明天"
                elif diff == 2:
                    day_label = "後天"
                else:
                    day_label = f"{d.month}/{d.day}"
                lines.append(f"\n📆 {day_label}（週{_WEEKDAY[d.weekday()]}）")
            lines.append(_fmt_event_line(ev))
        return "\n".join(lines)
    except Exception as e:
        print(f"[Google Calendar] 即將行程查詢失敗：{e}")
        return f"⚠️ 查詢失敗：{e}"


def _find_conflicts(service, start_iso: str, end_iso: str) -> list[str]:
    """回傳與指定時段重疊的行程名稱"""
    try:
        result = service.events().list(
            calendarId=_cal_id(),
            timeMin=start_iso, timeMax=end_iso,
            singleEvents=True, timeZone=TZ_NAME,
        ).execute()
        return [ev.get("summary", "（無標題）") for ev in result.get("items", [])]
    except Exception:
        return []


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
            conflict_warning = ""
        else:
            if not start_time.endswith("+08:00") and "T" in start_time:
                start_time += "+08:00"
            if end_time:
                if not end_time.endswith("+08:00") and "T" in end_time:
                    end_time += "+08:00"
            else:
                end_time = (datetime.fromisoformat(start_time) + timedelta(hours=1)).isoformat()

            # 衝突檢測
            conflicts = _find_conflicts(service, start_time, end_time)
            if conflicts:
                names = "、".join(f"「{c}」" for c in conflicts[:3])
                conflict_warning = f"\n⚠️ 注意：此時段已有 {names}"
            else:
                conflict_warning = ""

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
        if conflict_warning:
            result += conflict_warning
        return result
    except Exception as e:
        print(f"[Google Calendar] 新增失敗：{e}")
        return f"⚠️ 行程新增失敗：{e}"


def update_event(event_title: str, date_str: str | None = None,
                 new_title: str | None = None, new_start: str | None = None,
                 new_end: str | None = None, new_location: str | None = None,
                 new_description: str | None = None) -> str:
    """修改現有行程（標題、時間、地點、備註）"""
    service = _get_service()
    if not service:
        return "⚠️ Google Calendar 未設定"
    try:
        now = datetime.now(ZoneInfo(TZ_NAME))
        base = now
        if date_str:
            try:
                base = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=ZoneInfo(TZ_NAME))
            except ValueError:
                pass

        time_min = base.replace(hour=0, minute=0, second=0).isoformat()
        time_max = (base + timedelta(days=30)).isoformat()

        result = service.events().list(
            calendarId=_cal_id(),
            timeMin=time_min, timeMax=time_max,
            singleEvents=True, orderBy="startTime",
            q=event_title, timeZone=TZ_NAME,
        ).execute()
        events = result.get("items", [])
        if not events:
            return f"⚠️ 找不到標題包含「{event_title}」的行程（搜尋範圍：今天起 30 天內）"

        ev = events[0]
        patch = {}
        if new_title:
            patch["summary"] = new_title
        if new_location is not None:
            patch["location"] = new_location
        if new_description is not None:
            patch["description"] = new_description

        if new_start:
            is_all_day = len(new_start) == 10
            if is_all_day:
                patch["start"] = {"date": new_start}
                patch["end"] = {"date": new_end or new_start}
            else:
                if "T" in new_start and not new_start.endswith("+08:00"):
                    new_start += "+08:00"
                if new_end:
                    if "T" in new_end and not new_end.endswith("+08:00"):
                        new_end += "+08:00"
                else:
                    new_end = (datetime.fromisoformat(new_start) + timedelta(hours=1)).isoformat()
                patch["start"] = {"dateTime": new_start, "timeZone": TZ_NAME}
                patch["end"] = {"dateTime": new_end, "timeZone": TZ_NAME}

        if not patch:
            return "⚠️ 請指定要修改的內容（新標題、新時間、新地點或新備註）"

        service.events().patch(calendarId=_cal_id(), eventId=ev["id"], body=patch).execute()

        old_name = ev.get("summary", event_title)
        lines = ["✅ 行程已更新！", f"📌 {new_title or old_name}"]
        if new_start:
            st = datetime.fromisoformat(new_start)
            et = datetime.fromisoformat(new_end) if new_end else st + timedelta(hours=1)
            lines.append(f"📅 {st.strftime('%m/%d')} ⏰ {st.strftime('%H:%M')}~{et.strftime('%H:%M')}")
        if new_location:
            lines.append(f"📍 {new_location}")
        return "\n".join(lines)
    except Exception as e:
        print(f"[Google Calendar] 更新失敗：{e}")
        return f"⚠️ 行程更新失敗：{e}"


def check_free_busy(start_time: str, end_time: str) -> str:
    """查詢某時段是否有空（使用 freebusy API）"""
    service = _get_service()
    if not service:
        return "⚠️ Google Calendar 未設定"
    try:
        if "T" in start_time and not start_time.endswith("+08:00"):
            start_time += "+08:00"
        if "T" in end_time and not end_time.endswith("+08:00"):
            end_time += "+08:00"

        body = {
            "timeMin": start_time,
            "timeMax": end_time,
            "timeZone": TZ_NAME,
            "items": [{"id": _cal_id()}],
        }
        result = service.freebusy().query(body=body).execute()
        busy_times = result["calendars"].get(_cal_id(), {}).get("busy", [])

        st = datetime.fromisoformat(start_time)
        et = datetime.fromisoformat(end_time)
        time_range = f"{st.strftime('%m/%d')} {st.strftime('%H:%M')}~{et.strftime('%H:%M')}"

        if not busy_times:
            return f"✅ {time_range} 這個時段有空！可以安排行程。"

        lines = [f"❌ {time_range} 有行程衝突："]
        for busy in busy_times:
            bs = datetime.fromisoformat(busy["start"].replace("Z", "+00:00")).astimezone(ZoneInfo(TZ_NAME))
            be = datetime.fromisoformat(busy["end"].replace("Z", "+00:00")).astimezone(ZoneInfo(TZ_NAME))
            lines.append(f"  ⏰ {bs.strftime('%H:%M')}~{be.strftime('%H:%M')}")
        return "\n".join(lines)
    except Exception as e:
        print(f"[Google Calendar] 空閒查詢失敗：{e}")
        return f"⚠️ 查詢失敗：{e}"


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
