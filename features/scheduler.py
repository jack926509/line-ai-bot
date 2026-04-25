"""APScheduler 定時任務集中管理"""
import logging
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import db
from config import TZ_NAME, BRIEF_HOUR, BRIEF_MINUTE, DISABLE_SCHEDULER

logger = logging.getLogger("lumio.scheduler")

_scheduler: BackgroundScheduler | None = None


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
    _scheduler.start()
    logger.info(f"排程器啟動：早晨簡報 {BRIEF_HOUR:02d}:{BRIEF_MINUTE:02d} ({TZ_NAME})")


def shutdown_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("排程器已關閉")


def _morning_briefing_job() -> None:
    """每日 08:00 觸發：對所有訂閱簡報之使用者推送。"""
    from features.briefing import build_morning_briefing
    from features.push import push_text

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
