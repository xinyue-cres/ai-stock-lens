"""大盘/板块背景服务。

约定使用几个特定 code 作为"指数"存到同一张 kline_daily 里：
- sh000001  上证指数
- sz399001  深证成指
- sz399006  创业板指
- sh000300  沪深300

这样不用新增表，同步逻辑复用。数据源通过 DataRouter 的指数链路（东财→新浪）。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd
from sqlmodel import Session

from app.datasource.router import get_data_router
from app.models.kline import KlineDaily

logger = logging.getLogger(__name__)


def pct_change(series: pd.Series, period: int) -> float | None:
    if len(series) <= period:
        return None
    old = series.iloc[-period - 1]
    if old == 0:
        return None
    return round((series.iloc[-1] / old - 1) * 100, 2)

INDEX_CODES = {
    "sh000001": "上证指数",
    "sz399001": "深证成指",
    "sz399006": "创业板指",
    "sh000300": "沪深300",
}


def fetch_index_daily(code: str, start: date, end: date) -> pd.DataFrame:
    """拉指数日线。code 格式如 sh000001 / sz399001。"""
    return get_data_router().fetch_index_daily(code, start, end)


def sync_indices(session: Session, days: int = 365) -> int:
    """同步全部指数到本地库，返回新增行数。"""
    end = date.today()
    start = end - timedelta(days=days)
    total = 0
    for code in INDEX_CODES:
        try:
            df = fetch_index_daily(code, start, end)
            for _, row in df.iterrows():
                session.merge(
                    KlineDaily(
                        code=code,
                        trade_date=row["trade_date"],
                        open=float(row["open"]),
                        high=float(row["high"]),
                        low=float(row["low"]),
                        close=float(row["close"]),
                        volume=int(row["volume"] or 0),
                        amount=float(row["amount"] or 0),
                        turnover=None,
                        pct_chg=float(row["pct_chg"]) if pd.notna(row["pct_chg"]) else None,
                    )
                )
                total += 1
            session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("同步指数 %s 失败", code)
            session.rollback()
    return total


def get_market_context(session: Session) -> dict:
    """给 AI 用的大盘上下文快照。取每个指数的最新收盘 + 阶段涨幅。"""
    context: dict = {}
    from sqlmodel import select

    for code, name in INDEX_CODES.items():
        stmt = (
            select(KlineDaily)
            .where(KlineDaily.code == code)
            .order_by(KlineDaily.trade_date.desc())
            .limit(120)
        )
        rows = list(session.exec(stmt))
        if not rows:
            context[name] = {"empty": True}
            continue
        rows = list(reversed(rows))
        close = pd.Series([r.close for r in rows])
        context[name] = {
            "latest_close": float(close.iloc[-1]),
            "pct_1d": float(rows[-1].pct_chg) if rows[-1].pct_chg is not None else None,
            "pct_5d": pct_change(close, 5),
            "pct_20d": pct_change(close, 20),
            "pct_60d": pct_change(close, 60) if len(close) > 60 else None,
        }
    return context
