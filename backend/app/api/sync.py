from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends
from sqlmodel import Session, delete, select

from app.db import get_session
from app.models.kline import KlineDaily
from app.models.stock import Stock
from app.models.sync_log import SyncLog
from app.scheduler import get_scheduler_status
from app.services import sync_service

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/status")
def status(session: Session = Depends(get_session)):
    """一站式状态：调度器 + 最近一次同步。"""
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
def run_sync(session: Session = Depends(get_session)):
    log, rows_inserted, stocks_total = sync_service.sync_watchlist(session)
    return {
        "id": log.id,
        "status": log.status,
        "stocks_synced": log.stocks_synced,
        "stocks_total": stocks_total,
        "rows_inserted": rows_inserted,
        "error_msg": log.error_msg,
    }


@router.post("/stock/{code}")
def sync_single_stock(code: str, session: Session = Depends(get_session)):
    """同步单只股票的最新 K 线数据。"""
    rows = sync_service.sync_one_stock(session, code)
    return {"code": code, "rows_inserted": rows}


@router.post("/refresh-today")
def refresh_today(session: Session = Depends(get_session)):
    """强制重拉今日：删除所有自选股今日 K 线，再执行一次全量同步。

    用途：盘中一次同步落入了脏快照(pct=0/volume 异常等)，用户点这个按钮清掉今日行强制重拉。
    """
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

    log, rows_inserted, stocks_total = sync_service.sync_watchlist(session)
    return {
        "id": log.id,
        "status": log.status,
        "stocks_synced": log.stocks_synced,
        "stocks_total": stocks_total,
        "rows_inserted": rows_inserted,
        "rows_deleted": deleted,
        "error_msg": log.error_msg,
    }


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
