"""APScheduler 定時任務（個人版：僅保留 DB 維護，所有推播通知已停用）。"""
import logging
from contextlib import contextmanager
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import db
from config import TZ_NAME, DISABLE_SCHEDULER
from db.pool import get_db

logger = logging.getLogger("lumio.scheduler")

_scheduler: BackgroundScheduler | None = None

# Advisory lock keys（任意常數，需於所有副本一致）
_LOCK_CLEANUP = 7301_002


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
    # 每日 03:30 清理過期紀錄（push_log / processed_messages / token_usage / workflows）
    _scheduler.add_job(
        _cleanup_job,
        CronTrigger(hour=3, minute=30),
        id="db_cleanup",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info("排程器啟動（個人版：僅 DB 維護任務）")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("排程器已關閉")


def register_one_off(when, callback, args: list | None = None, job_id: str | None = None) -> None:
    """登記一次性任務（預留給未來通知系統使用）。"""
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
