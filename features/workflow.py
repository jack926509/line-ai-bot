"""提醒（Reminder）：一次性 / 每日 / 每週。

由 features/scheduler.py 每分鐘 tick 觸發到期項目。
時間採台北時區（Asia/Taipei）；DB 儲存 UTC 以避開時區陷阱。
"""
import logging
from datetime import datetime, time as dtime, timedelta
from zoneinfo import ZoneInfo

import db
from config import TZ_NAME

logger = logging.getLogger("lumio.workflow")

_TZ = ZoneInfo(TZ_NAME)


def _parse_hhmm(s: str) -> tuple[int, int] | None:
    if not s or ":" not in s:
        return None
    try:
        h, m = s.split(":")
        h, m = int(h), int(m)
    except ValueError:
        return None
    if not (0 <= h < 24 and 0 <= m < 60):
        return None
    return h, m


def _next_daily(spec: str, ref: datetime) -> datetime | None:
    """計算 spec='HH:MM' 在 ref 之後的最近一次觸發（台北時間）。"""
    hm = _parse_hhmm(spec)
    if not hm:
        return None
    h, m = hm
    local = ref.astimezone(_TZ)
    candidate = local.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= local:
        candidate += timedelta(days=1)
    return candidate


def _next_weekly(spec: str, ref: datetime) -> datetime | None:
    """spec='N|HH:MM'，N=1..7（1=週一），回傳下一次觸發時間。"""
    if "|" not in spec:
        return None
    n_str, hhmm = spec.split("|", 1)
    try:
        n = int(n_str)
    except ValueError:
        return None
    if not (1 <= n <= 7):
        return None
    hm = _parse_hhmm(hhmm)
    if not hm:
        return None
    h, m = hm
    local = ref.astimezone(_TZ)
    # weekday(): Mon=0..Sun=6；spec 採 1=Mon..7=Sun → weekday = n-1
    target_wd = n - 1
    days_ahead = (target_wd - local.weekday()) % 7
    candidate = local.replace(hour=h, minute=m, second=0, microsecond=0) + timedelta(days=days_ahead)
    if candidate <= local:
        candidate += timedelta(days=7)
    return candidate


def _compute_next(steps: dict, ref: datetime) -> datetime | None:
    kind = steps.get("kind")
    spec = steps.get("spec", "")
    if kind == "daily":
        return _next_daily(spec, ref)
    if kind == "weekly":
        return _next_weekly(spec, ref)
    return None  # once 不再排下次


# ── Claude tool 入口 ──────────────────────────────


def reminder_add_once(user_id: str, text: str, when_iso: str) -> str:
    """一次性提醒。when_iso 為 ISO 格式（含或不含時區，無時區視為台北）。"""
    try:
        when = datetime.fromisoformat(when_iso)
    except ValueError:
        return f"⚠️ 時間格式錯誤：{when_iso}（應為 YYYY-MM-DDTHH:MM）"
    if when.tzinfo is None:
        when = when.replace(tzinfo=_TZ)
    if when <= datetime.now(_TZ):
        return "⚠️ 時間已過去，請指定未來的時間"
    steps = {"kind": "once", "text": text}
    wf_id = db.add_workflow(user_id, text[:50], steps, when)
    local = when.astimezone(_TZ).strftime("%Y-%m-%d %H:%M")
    return f"⏰ 已排定提醒（id={wf_id}）：{local}\n　{text}"


def reminder_add_daily(user_id: str, text: str, hhmm: str) -> str:
    """每日提醒，hhmm='HH:MM'。"""
    if not _parse_hhmm(hhmm):
        return f"⚠️ 時間格式錯誤：{hhmm}（應為 HH:MM）"
    steps = {"kind": "daily", "text": text, "spec": hhmm}
    next_run = _next_daily(hhmm, datetime.now(_TZ))
    wf_id = db.add_workflow(user_id, text[:50], steps, next_run)
    return f"⏰ 已排定每日提醒（id={wf_id}）：{hhmm}\n　{text}"


_WEEKDAY_LABEL = {1: "週一", 2: "週二", 3: "週三", 4: "週四", 5: "週五", 6: "週六", 7: "週日"}


def reminder_add_weekly(user_id: str, text: str, weekday: int, hhmm: str) -> str:
    """每週提醒，weekday=1..7（1=週一）。"""
    if not (1 <= weekday <= 7):
        return f"⚠️ weekday 必須 1-7（1=週一）：{weekday}"
    if not _parse_hhmm(hhmm):
        return f"⚠️ 時間格式錯誤：{hhmm}"
    spec = f"{weekday}|{hhmm}"
    steps = {"kind": "weekly", "text": text, "spec": spec}
    next_run = _next_weekly(spec, datetime.now(_TZ))
    wf_id = db.add_workflow(user_id, text[:50], steps, next_run)
    return (f"⏰ 已排定每週提醒（id={wf_id}）：{_WEEKDAY_LABEL[weekday]} {hhmm}\n　{text}")


def reminder_list(user_id: str) -> str:
    rows = db.list_workflows(user_id, include_done=False)
    rows = [r for r in rows if r[3] == "pending"]
    if not rows:
        return "⏰ 沒有待執行的提醒"
    lines = ["⏰ 提醒清單："]
    for wid, name, steps, _state, next_run in rows:
        kind = (steps or {}).get("kind", "once")
        if isinstance(steps, str):
            import json
            try:
                steps = json.loads(steps)
                kind = steps.get("kind", "once")
            except Exception:
                pass
        nr = next_run.astimezone(_TZ).strftime("%m/%d %H:%M") if next_run else "-"
        kind_label = {"once": "一次", "daily": "每日", "weekly": "每週"}.get(kind, kind)
        lines.append(f"  [{wid}] {nr}  {kind_label}  {name}")
    return "\n".join(lines)


def reminder_cancel(user_id: str, wf_id: int) -> str:
    name = db.cancel_workflow(user_id, wf_id)
    return f"🗑 已取消提醒：「{name}」" if name else f"⚠️ 找不到 id={wf_id} 或已執行"


# ── 排程器觸發入口 ────────────────────────────────


def tick(now: datetime | None = None) -> int:
    """掃描到期工作流並推播。回傳處理筆數。"""
    from features.push import push_text

    now = now or datetime.now(_TZ)
    # DB 比較用 UTC（PG 內部處理 timestamptz；保險用本地時間也可，這裡用 now）
    rows = db.workflows_fetch_due(now)
    if not rows:
        return 0

    processed = 0
    for wf_id, user_id, name, steps, _next in rows:
        try:
            steps_obj = steps if isinstance(steps, dict) else (steps or {})
            text = steps_obj.get("text") or name
            push_text(user_id, f"⏰ 提醒：{text}")
            kind = steps_obj.get("kind", "once")
            if kind == "once":
                db.workflow_mark_done(wf_id)
            else:
                next_run = _compute_next(steps_obj, now)
                if next_run is None:
                    db.workflow_mark_done(wf_id)
                else:
                    db.workflow_update_next_run(wf_id, next_run)
            processed += 1
            logger.info(f"reminder fired wf_id={wf_id} user={user_id} kind={kind}")
        except Exception as e:
            logger.exception(f"reminder 處理失敗 wf_id={wf_id}: {e}")
    return processed


# ── 既有 compose_workflow 保留為佔位（未來多步驟編排） ──


def compose_workflow(goal: str, steps: list[dict] | None = None) -> str:
    return (
        "🚧 多步驟工作流（即將推出）\n\n"
        f"目標：{goal}\n\n"
        "目前可用的提醒功能：reminder_add_once / reminder_add_daily / reminder_add_weekly。"
    )
