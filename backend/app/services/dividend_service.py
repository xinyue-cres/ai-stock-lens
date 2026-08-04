"""股息率缓存服务：拉取 + 落 StockDividend 缓存（30 天刷新）。

数据源纯拉取在 datasource/dividend_provider（无数据库依赖），本模块负责
缓存读写、ETF/LOF 过滤与过期刷新。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlmodel import select

from app.datasource.base_provider import is_fund_code
from app.datasource.dividend_provider import fetch_dividend_map
from app.models.stock_dividend import StockDividend

logger = logging.getLogger(__name__)

_CACHE_DAYS = 30
_YEARS = 3  # 参与平均的年度数（与 datasource 拉取口径一致）


def _save(session, code: str, avg_yield: float | None) -> None:
    row = session.get(StockDividend, code)
    if row is None:
        row = StockDividend(code=code)
    row.avg_yield_3y = avg_yield
    row.years = _YEARS if avg_yield is not None else 0
    row.updated_at = date.today()
    session.add(row)


def load_dividend_map(session, codes: list[str]) -> dict[str, float | None]:
    """批量取近 3 年平均股息率 map：{code: 股息率(%) | None}。

    优先读 StockDividend 缓存（30 天内），缺失/过期的批量拉取并写回。
    ETF/LOF 直接返回 None（无分红表）。
    """
    if not codes:
        return {}
    stock_codes = [c for c in codes if not is_fund_code(c)]
    if not stock_codes:
        return {}

    result: dict[str, float | None] = {}
    stale: list[str] = []
    today = date.today()
    for code in stock_codes:
        row = session.get(StockDividend, code)
        if row and row.avg_yield_3y is not None and (today - row.updated_at).days < _CACHE_DAYS:
            result[code] = row.avg_yield_3y
        else:
            stale.append(code)

    if stale:
        fresh = fetch_dividend_map(stale)
        for code, y in fresh.items():
            result[code] = y
            _save(session, code, y)
        try:
            session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("写入股息缓存失败")
            session.rollback()

    return result


def get_dividend_yield(session, code: str) -> float | None:
    """单只查询（薄封装 load_dividend_map）。"""
    return load_dividend_map(session, [code]).get(code)


def purge_dividend_cache(session, days: int = _CACHE_DAYS) -> int:
    """清理超过 days 天未刷新的缓存行，返回清理条数。供扫描前主动刷新用。"""
    cutoff = date.today() - timedelta(days=days)
    rows = session.exec(select(StockDividend).where(StockDividend.updated_at < cutoff)).all()
    for row in rows:
        session.delete(row)
    session.commit()
    return len(rows)
