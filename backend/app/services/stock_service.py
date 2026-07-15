"""股票元数据服务。"""
from __future__ import annotations

import logging

from sqlmodel import Session, select

from app.datasource.router import get_data_router
from app.models.stock import Stock

logger = logging.getLogger(__name__)


def ensure_stock(session: Session, code: str) -> Stock:
    """从库中取或从数据源查一次并入库。"""
    stock = session.get(Stock, code)
    if stock:
        return stock

    for info in get_data_router().get_stock_list():
        if info.code == code:
            stock = Stock(code=info.code, name=info.name, market=info.market)
            session.add(stock)
            session.commit()
            session.refresh(stock)
            return stock

    raise ValueError(f"股票代码 {code} 不存在")


def refresh_stock_index(session: Session) -> int:
    """从数据源拉全 A 股列表填充到 stock 表，返回新增数量。"""
    infos = get_data_router().get_stock_list()
    added = 0
    for info in infos:
        existing = session.get(Stock, info.code)
        if existing is None:
            session.add(Stock(code=info.code, name=info.name, market=info.market))
            added += 1
        elif existing.name != info.name:
            existing.name = info.name
            session.add(existing)
    session.commit()
    if added:
        logger.info("股票元数据补齐：新增 %d 条", added)
    return added


def _count_stocks(session: Session) -> int:
    from sqlalchemy import func

    return session.exec(select(func.count()).select_from(Stock)).one()


def search_stocks(session: Session, keyword: str, limit: int = 20) -> list[Stock]:
    if _count_stocks(session) < 100:
        # 首次或几乎为空的库，先补齐全量元数据
        try:
            refresh_stock_index(session)
        except Exception:
            logger.exception("补齐股票元数据失败")
    stmt = (
        select(Stock)
        .where((Stock.name.contains(keyword)) | (Stock.code.contains(keyword)))
        .limit(limit)
    )
    return list(session.exec(stmt))


def list_watchlist(session: Session) -> list[Stock]:
    return list(session.exec(select(Stock).where(Stock.is_watchlist == True)))  # noqa: E712


def add_to_watchlist(session: Session, code: str) -> Stock:
    stock = ensure_stock(session, code)
    stock.is_watchlist = True
    session.add(stock)
    session.commit()
    session.refresh(stock)
    return stock


def remove_from_watchlist(session: Session, code: str) -> None:
    stock = session.get(Stock, code)
    if stock:
        stock.is_watchlist = False
        stock.pinned = False
        session.add(stock)
        session.commit()


def set_pinned(session: Session, code: str, pinned: bool) -> Stock | None:
    stock = session.get(Stock, code)
    if not stock:
        return None
    stock.pinned = pinned
    session.add(stock)
    session.commit()
    session.refresh(stock)
    return stock
