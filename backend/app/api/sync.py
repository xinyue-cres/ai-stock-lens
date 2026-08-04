from __future__ import annotations

import logging
import time
from datetime import date, datetime

from fastapi import APIRouter, BackgroundTasks, Depends
from sqlmodel import Session, delete, select

from app.db import engine, get_session
from app.models.kline import KlineDaily
from app.models.stock import Stock
from app.models.sync_log import SyncLog
from app.scheduler import get_scheduler_status
from app.services import sync_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])

# 全量同步是重任务（61 只串行拉 K 线可超 90s），必须后台异步执行，否则前端 60s 请求超时。
# 同步状态通过 /sync/status 的 SyncLog 查询；进程重启中断的"僵尸 running"自动清理。
_ZOMBIE_SYNC_MINUTES = 30
# 模块加载时间 ≈ 进程启动时间：进程重启后旧后台同步线程必然死亡，凡 started_at 早于
# 本进程启动的 running 记录都是僵尸，可安全清理（不必等 30 分钟）
_PROCESS_START_DT = datetime.fromtimestamp(time.time())


def _background_sync_watchlist() -> None:
    """后台全量同步（请求已返回，用独立 session 执行）。"""
    from sqlmodel import Session as S

    try:
        with S(engine) as s:
            sync_service.sync_watchlist(s)
        logger.info("后台全量同步完成")
    except Exception:  # noqa: BLE001
        logger.exception("后台全量同步失败")


def _cleanup_zombie_sync(session: Session) -> None:
    """清理僵尸同步记录：进程重启中断（started_at 早于本进程启动）或超时（>30 分钟）仍 running。"""
    rows = session.exec(select(SyncLog).where(SyncLog.finished_at.is_(None))).all()
    changed = False
    for r in rows:
        zombie = False
        if r.started_at:
            if r.started_at < _PROCESS_START_DT:
                zombie = True  # 本进程启动前就在跑 → 旧线程已随进程重启死亡
            elif (datetime.now() - r.started_at).total_seconds() > _ZOMBIE_SYNC_MINUTES * 60:
                zombie = True
        if zombie:
            r.finished_at = datetime.now()
            r.status = "failed"
            r.error_msg = (r.error_msg or "") + "\n(僵尸同步：进程重启或超时中断，自动标记)"
            session.add(r)
            changed = True
    if changed:
        session.commit()


def _is_sync_running(session: Session) -> bool:
    """是否有正在进行的同步（含 30 分钟内刚启动的，防并发重入）。"""
    _cleanup_zombie_sync(session)
    last = session.exec(select(SyncLog).order_by(SyncLog.started_at.desc()).limit(1)).first()
    return last is not None and last.finished_at is None


@router.get("/status")
def status(session: Session = Depends(get_session)):
    """一站式状态：调度器 + 最近一次同步。"""
    _cleanup_zombie_sync(session)
    sched = get_scheduler_status()
    last = session.exec(select(SyncLog).order_by(SyncLog.started_at.desc()).limit(1)).first()
    return {
        "scheduler": sched,
        "last_sync": (
            {
                "id": last.id,
                "started_at": last.started_at,
                "finished_at": last.finished_at,
                "status": last.status,
                "stocks_synced": last.stocks_synced,
                "error_msg": last.error_msg,
            }
            if last
            else None
        ),
    }


@router.post("/run")
def run_sync(background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    """全量同步：后台异步执行，立即返回。进度/结果看 /sync/status（防并发重入）。"""
    if _is_sync_running(session):
        return {"started": False, "status": "running", "reason": "已有同步进行中"}
    background_tasks.add_task(_background_sync_watchlist)
    return {"started": True, "status": "running"}


@router.post("/stock/{code}")
def sync_single_stock(code: str, session: Session = Depends(get_session)):
    """同步单只股票的最新 K 线数据 + 大盘指数（5分钟冷却）。"""
    from app.services.sync_service import _sync_indices_if_due
    _sync_indices_if_due(session)
    rows = sync_service.sync_one_stock(session, code)
    return {"code": code, "rows_inserted": rows}


@router.post("/refresh-today")
def refresh_today(background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    """强制重拉今日：删今日行后后台全量同步（异步，立即返回）。

    用途：盘中一次同步落入了脏快照(pct=0/volume 异常等)，用户点这个按钮清掉今日行强制重拉。
    """
    if _is_sync_running(session):
        return {"started": False, "status": "running", "reason": "已有同步进行中", "rows_deleted": 0}
    today = date.today()
    stocks = list(session.exec(select(Stock).where(Stock.is_watchlist == True)))  # noqa: E712
    deleted = 0
    for stock in stocks:
        result = session.exec(
            delete(KlineDaily).where(
                KlineDaily.code == stock.code, KlineDaily.trade_date == today
            )
        )
        deleted += getattr(result, "rowcount", 0) or 0
    session.commit()

    background_tasks.add_task(_background_sync_watchlist)
    return {"started": True, "status": "running", "rows_deleted": deleted}


@router.post("/indices")
def sync_indices(session: Session = Depends(get_session)):
    """同步大盘指数（上证/深证成指/创业板指/沪深300）到本地。"""
    from app.services.market_service import sync_indices as _sync

    rows = _sync(session)
    return {"rows": rows}


@router.get("/logs")
def list_logs(limit: int = 20, session: Session = Depends(get_session)):
    stmt = select(SyncLog).order_by(SyncLog.started_at.desc()).limit(limit)
    rows = list(session.exec(stmt))
    return [
        {
            "id": r.id,
            "started_at": r.started_at,
            "finished_at": r.finished_at,
            "status": r.status,
            "stocks_synced": r.stocks_synced,
            "error_msg": r.error_msg,
        }
        for r in rows
    ]


@router.get("/datasource-health")
def datasource_health():
    """各数据源 provider 当前健康状态：熔断、失败次数、冷却剩余。"""
    from app.datasource import get_data_router

    dr = get_data_router()
    return {"providers": dr.get_health()}
