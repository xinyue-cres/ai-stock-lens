from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel
from sqlmodel import Session

from app.db import engine, get_session
from app.services import position_service, stock_service, sync_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class WatchlistAdd(BaseModel):
    code: str


@router.get("")
def get_watchlist(session: Session = Depends(get_session)):
    stocks = stock_service.list_watchlist(session)
    codes = [s.code for s in stocks]
    positions = position_service.get_positions_by_codes(session, codes)
    result = []
    for s in stocks:
        item = {"code": s.code, "name": s.name, "market": s.market, "pinned": bool(s.pinned)}
        pos = positions.get(s.code)
        if pos and pos.quantity > 0:
            item["position"] = position_service.summarize(session, pos)
        result.append(item)
    return result


def _background_sync(code: str) -> None:
    """加入自选股后，异步全量同步一次，避免用户还要手动点。"""
    from sqlmodel import Session as S
    try:
        with S(engine) as s:
            sync_service.sync_one_stock(s, code, full=True)
        logger.info("自选股 %s 首次同步完成", code)
    except Exception:  # noqa: BLE001
        logger.exception("自选股 %s 首次同步失败", code)


@router.post("")
def add_watch(
    payload: WatchlistAdd,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session),
):
    stock = stock_service.add_to_watchlist(session, payload.code)
    background_tasks.add_task(_background_sync, stock.code)
    return {"code": stock.code, "name": stock.name, "syncing": True}


@router.delete("/{code}")
def remove_watch(code: str, session: Session = Depends(get_session)):
    stock_service.remove_from_watchlist(session, code)
    return {"ok": True}


class PinPayload(BaseModel):
    pinned: bool


@router.patch("/{code}/pin")
def set_pin(code: str, payload: PinPayload, session: Session = Depends(get_session)):
    stock = stock_service.set_pinned(session, code, payload.pinned)
    if not stock:
        return {"ok": False, "reason": "not found"}
    return {"ok": True, "code": stock.code, "pinned": stock.pinned}
