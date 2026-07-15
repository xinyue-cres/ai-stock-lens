"""APScheduler 定时任务。"""
from __future__ import annotations

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlmodel import Session

from app.config import get_settings
from app.db import engine
from app.services.review_service import review_all_pending
from app.services.sync_service import sync_watchlist

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def _job_sync_watchlist() -> None:
    logger.info("定时任务：开始同步自选股")
    try:
        with Session(engine) as session:
            log, rows, total = sync_watchlist(session)
        logger.info(
            "同步完成 status=%s stocks=%d/%d rows=%d",
            log.status, log.stocks_synced, total, rows,
        )
    except Exception:  # noqa: BLE001
        logger.exception("定时同步失败")


def _job_review_all() -> None:
    logger.info("定时任务：开始复盘所有 AI 报告")
    try:
        with Session(engine) as session:
            stats = review_all_pending(session)
        logger.info("复盘完成 reports=%d new_reviews=%d", stats["reports"], stats["new_reviews"])
    except Exception:  # noqa: BLE001
        logger.exception("定时复盘失败")


def start_scheduler() -> None:
    global _scheduler
    settings = get_settings()
    if not settings.sync_enabled:
        logger.info("SYNC_ENABLED=false，跳过调度器启动")
        return

    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")
    _scheduler.add_job(
        _job_sync_watchlist,
        trigger=CronTrigger(
            hour=settings.sync_cron_hour,
            minute=settings.sync_cron_minute,
            day_of_week="mon-fri",
        ),
        id="sync_watchlist",
        replace_existing=True,
    )
    # 同步完约 10 分钟后跑复盘（此时新的日线已入库）
    review_minute = (settings.sync_cron_minute + 10) % 60
    review_hour = settings.sync_cron_hour + ((settings.sync_cron_minute + 10) // 60)
    _scheduler.add_job(
        _job_review_all,
        trigger=CronTrigger(
            hour=review_hour,
            minute=review_minute,
            day_of_week="mon-fri",
        ),
        id="review_all",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info(
        "调度器已启动 · 同步 %02d:%02d · 复盘 %02d:%02d",
        settings.sync_cron_hour,
        settings.sync_cron_minute,
        review_hour,
        review_minute,
    )


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None


def get_scheduler_status() -> dict:
    """返回调度器的运行状态供前端展示。"""
    settings = get_settings()
    if not _scheduler or not _scheduler.running:
        return {
            "running": False,
            "enabled": settings.sync_enabled,
            "cron_hour": settings.sync_cron_hour,
            "cron_minute": settings.sync_cron_minute,
            "next_run_at": None,
        }
    job = _scheduler.get_job("sync_watchlist")
    return {
        "running": True,
        "enabled": True,
        "cron_hour": settings.sync_cron_hour,
        "cron_minute": settings.sync_cron_minute,
        "next_run_at": job.next_run_time.isoformat() if job and job.next_run_time else None,
        "job_id": job.id if job else None,
    }
