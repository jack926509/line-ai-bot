"""旅遊行程組合：trips 表 + 自動雙寫 Google Calendar"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import db
from config import TZ_NAME
from features.calendar import _get_service, _cal_id

logger = logging.getLogger("lumio.trip")


def trip_create(
    user_id: str,
    name: str,
    start_date: str,
    end_date: str,
    places: list[dict],
) -> str:
    """建立旅程：寫 trips 表 + 為每個 place 在 Google Calendar 建一筆事件。

    places: [{day: 1, time: "09:00", name: "太宰府", note: "...", location: "..."}, ...]
      day 為相對於 start_date 的第幾天（1-based）；time 為 24h "HH:MM"，可省略代表整天。
    """
    try:
        sd = datetime.strptime(start_date, "%Y-%m-%d").date()
        ed = datetime.strptime(end_date, "%Y-%m-%d").date()
    except Exception:
        return "⚠️ 日期格式應為 YYYY-MM-DD"

    if ed < sd:
        return "⚠️ 結束日期不可早於開始日期"

    service = _get_service()
    if service is None:
        return "⚠️ Google Calendar 未設定，無法寫入行程"

    gcal_ids = []
    written = 0
    skipped: list[str] = []
    failed: list[str] = []
    for p in places or []:
        try:
            day = int(p.get("day", 1))
            place_name = p.get("name", "").strip()
            time_str = (p.get("time") or "").strip()
            note = p.get("note", "")
            location = p.get("location") or place_name
            if not place_name:
                continue
            if day < 1:
                skipped.append(f"D{day} {place_name}（日序須 ≥ 1）")
                continue
            ev_date = sd + timedelta(days=day - 1)
            if ev_date > ed:
                skipped.append(f"D{day} {place_name}（超出旅程結束日 {end_date}）")
                continue

            title = f"[{name}] {place_name}"
            if time_str:
                start_iso = f"{ev_date.isoformat()}T{time_str}:00+08:00"
                end_iso = (datetime.fromisoformat(start_iso) + timedelta(hours=2)).isoformat()
                body = {
                    "summary": title,
                    "location": location,
                    "description": note,
                    "start": {"dateTime": start_iso, "timeZone": TZ_NAME},
                    "end":   {"dateTime": end_iso,   "timeZone": TZ_NAME},
                }
            else:
                body = {
                    "summary": title,
                    "location": location,
                    "description": note,
                    "start": {"date": ev_date.isoformat()},
                    "end":   {"date": (ev_date + timedelta(days=1)).isoformat()},
                }
            result = service.events().insert(calendarId=_cal_id(), body=body).execute()
            gcal_ids.append(result["id"])
            written += 1
        except Exception as e:
            logger.warning(f"寫入 GCal 失敗 place={p}: {e}")
            failed.append(f"D{p.get('day', '?')} {p.get('name', '')}：{e}")

    trip_id = db.add_trip(user_id, name, start_date, end_date, places, gcal_ids)
    lines = [
        f"✈️ 旅程已建立:「{name}」",
        f"📅 {start_date} ~ {end_date}",
        f"📍 {written} / {len(places)} 個地點已寫入 Google Calendar",
    ]
    if skipped:
        lines.append("")
        lines.append(f"⚠️ 已跳過 {len(skipped)} 個地點:")
        for s in skipped[:5]:
            lines.append(f"  • {s}")
        if len(skipped) > 5:
            lines.append(f"  …另有 {len(skipped) - 5} 個未列出")
    if failed:
        lines.append("")
        lines.append(f"⚠️ {len(failed)} 個地點寫入失敗:")
        for f in failed[:3]:
            lines.append(f"  • {f}")
    lines.append(f"trip #{trip_id} — 用「我的旅程」或 /旅遊 查看")
    return "\n".join(lines)


def trip_list(user_id: str) -> str:
    rows = db.list_trips(user_id)
    if not rows:
        return "✈️ 還沒有任何旅程\n說「規劃 7/15-19 福岡，想去太宰府⋯」即可建立"
    lines = ["✈️ 旅程清單："]
    for i, (_id, name, sd, ed, places, _gcal) in enumerate(rows, 1):
        n = len(places) if places else 0
        lines.append(f"  {i}. {name}（{sd} ~ {ed}，{n} 個地點）")
    return "\n".join(lines)


def trip_detail(user_id: str, index: int) -> str:
    rows = db.list_trips(user_id)
    if index < 1 or index > len(rows):
        return "⚠️ 找不到該編號的旅程"
    _id, name, sd, ed, places, _gcal = rows[index - 1]
    lines = [f"✈️ {name}", f"📅 {sd} ~ {ed}", ""]
    if not places:
        lines.append("（無地點）")
    else:
        for p in places:
            day = p.get("day", 1)
            time_str = p.get("time", "")
            place = p.get("name", "")
            note = p.get("note", "")
            stamp = f"D{day}" + (f" {time_str}" if time_str else " 整天")
            line = f"  {stamp} 📍 {place}"
            if note:
                line += f" — {note}"
            lines.append(line)
    return "\n".join(lines)


def trip_delete(user_id: str, index: int) -> str:
    rows = db.list_trips(user_id)
    if index < 1 or index > len(rows):
        return "⚠️ 找不到該編號的旅程"
    trip_id, name, _sd, _ed, _places, gcal_ids = rows[index - 1]

    deleted_count = 0
    service = _get_service()
    if service is not None and gcal_ids:
        for ev_id in gcal_ids:
            try:
                service.events().delete(calendarId=_cal_id(), eventId=ev_id).execute()
                deleted_count += 1
            except Exception as e:
                logger.warning(f"GCal 刪除失敗 event={ev_id}: {e}")

    db.delete_trip(trip_id)
    suffix = ""
    if gcal_ids:
        suffix = f"\nGoogle Calendar 已同步刪除 {deleted_count}/{len(gcal_ids)} 筆"
    return f"🗑 已刪除旅程：「{name}」{suffix}"


# ─── /旅遊 slash 入口 ───

def handle_trip(text: str, user_id: str) -> str:
    import re
    parts = text.split(maxsplit=1)
    arg = parts[1].strip() if len(parts) > 1 else ""

    if not arg:
        return trip_list(user_id)
    m = re.match(r"(查看|看|view)\s*(\d+)$", arg)
    if m:
        return trip_detail(user_id, int(m.group(2)))
    m = re.match(r"(刪除?|delete|x)\s*(\d+)$", arg)
    if m:
        return trip_delete(user_id, int(m.group(2)))
    return (
        "✈️ /旅遊 用法：\n"
        "  /旅遊           查看清單\n"
        "  /旅遊 查看 N    第 N 趟詳情\n"
        "  /旅遊 刪 N      刪除第 N 趟（GCal 同步刪）\n"
        "新增旅程請改說：「規劃 7/15-19 福岡，第一天太宰府...」"
    )
