"""APScheduler 定時任務集中管理"""
import logging
from contextlib import contextmanager
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import db
from config import TZ_NAME, BRIEF_HOUR, BRIEF_MINUTE, DISABLE_SCHEDULER
from db.pool import get_db

logger = logging.getLogger("lumio.scheduler")

_scheduler: BackgroundScheduler | None = None

# Advisory lock keys（任意常數，需於所有副本一致）
_LOCK_BRIEFING = 7301_001
_LOCK_CLEANUP = 7301_002
_LOCK_REMINDER = 7301_003


@contextmanager
def _advisory_lock(key: int):
    """以 PG advisory lock 確保多副本部署時同任務只有一節點執行。"""
    with get_db() as conn:
        cur = conn.cursor()
        cur.execute("SELECT pg_try_advisory_lock(%s)", (key,))
        acquired = bool(cur.fetchone()[0])
        try:
            yield acquired
        finally:
            if acquired:
                cur.execute("SELECT pg_advisory_unlock(%s)", (key,))


def start_scheduler() -> None:
    """於 FastAPI lifespan 中呼叫以啟動排程器。"""
    global _scheduler
    if DISABLE_SCHEDULER:
        logger.info("DISABLE_SCHEDULER=True，跳過排程器啟動")
        return
    if _scheduler is not None:
        return

    _scheduler = BackgroundScheduler(timezone=ZoneInfo(TZ_NAME))
    _scheduler.add_job(
        _morning_briefing_job,
        CronTrigger(hour=BRIEF_HOUR, minute=BRIEF_MINUTE),
        id="morning_briefing",
        replace_existing=True,
        misfire_grace_time=600,
    )
    # 每日 03:30 清理超過 90 天的推播紀錄
    _scheduler.add_job(
        _cleanup_job,
        CronTrigger(hour=3, minute=30),
        id="push_log_cleanup",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # 每分鐘 tick 提醒到期工作流
    _scheduler.add_job(
        _reminder_tick_job,
        CronTrigger(minute="*"),
        id="reminder_tick",
        replace_existing=True,
        misfire_grace_time=60,
    )
    _scheduler.start()
    logger.info(f"排程器啟動：早晨簡報 {BRIEF_HOUR:02d}:{BRIEF_MINUTE:02d} ({TZ_NAME})")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("排程器已關閉")


def register_one_off(when, callback, args: list | None = None, job_id: str | None = None) -> None:
    """登記一次性任務（預留給多步驟工作流使用）。

    when: datetime 物件
    callback: 任意 callable
    args: callback 參數列
    job_id: 自訂 id；若提供則 replace_existing=True
    """
    if _scheduler is None:
        logger.warning("scheduler 未啟動，one-off 任務未登記")
        return
    from apscheduler.triggers.date import DateTrigger
    _scheduler.add_job(
        callback,
        DateTrigger(run_date=when),
        args=args or [],
        id=job_id,
        replace_existing=bool(job_id),
    )
    logger.info(f"one-off 任務已登記 when={when} id={job_id}")


def _morning_briefing_job() -> None:
    """每日 08:00 觸發：對所有訂閱簡報之使用者推送。

    多副本部署時，僅持有 PG advisory lock 之節點實際執行；
    push_log 為次層去重保險（同 user_id+kind+ref_date 唯一）。
    """
    from features.briefing import build_morning_briefing
    from features.push import push_text

    with _advisory_lock(_LOCK_BRIEFING) as acquired:
        if not acquired:
            logger.info("簡報任務 advisory lock 未取得，跳過（其他節點執行中）")
            return

        subs = db.get_briefing_subscribers()
        logger.info(f"執行早晨簡報推送，訂閱數={len(subs)}")
        for uid in subs:
            if db.has_pushed_today(uid, "briefing"):
                continue
            try:
                msg = build_morning_briefing(uid)
                if push_text(uid, msg):
                    db.mark_pushed(uid, "briefing")
                    logger.info(f"簡報已推送 user={uid}")
            except Exception as e:
                logger.exception(f"簡報失敗 user={uid}: {e}")


def _cleanup_job() -> None:
    """定期清理推播紀錄與訊息去重表；advisory lock 確保多副本下只有一節點執行。"""
    with _advisory_lock(_LOCK_CLEANUP) as acquired:
        if not acquired:
            return
        try:
            db.cleanup_push_log(retention_days=90)
        except Exception as e:
            logger.warning(f"push_log 清理失敗: {e}")
        try:
            db.cleanup_processed_messages(retention_days=7)
        except Exception as e:
            logger.warning(f"processed_messages 清理失敗: {e}")
        try:
            db.cleanup_token_usage(retention_days=365)
        except Exception as e:
            logger.warning(f"token_usage 清理失敗: {e}")
        try:
            db.cleanup_workflows(retention_days=30)
        except Exception as e:
            logger.warning(f"workflows 清理失敗: {e}")


def _reminder_tick_job() -> None:
    """每分鐘觸發到期提醒；advisory lock 防多副本重送。"""
    from features.workflow import tick
    with _advisory_lock(_LOCK_REMINDER) as acquired:
        if not acquired:
            return
        try:
            n = tick()
            if n:
                logger.info(f"reminder tick 處理 {n} 筆")
        except Exception as e:
            logger.warning(f"reminder tick 失敗: {e}")
