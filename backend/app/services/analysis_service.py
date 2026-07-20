"""分析服务：从库取 K 线 → 算指标 → 组合返回。

缓存说明：指纹用最近 5 行 K 线的字段内容 hash，只要 open/high/low/close/volume/
amount/turnover/pct_chg 任何一个改了指纹就变，无需手动 invalidate。回填、盘中
修正、增量同步等所有改动都会自动触发失效。
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta

import pandas as pd
from sqlmodel import Session, select

from app.indicators.engine import build_chart_series, compute_all
from app.indicators.signals import scan_signals
from app.indicators.weekly import aggregate_weekly
from app.models.kline import KlineDaily
from app.models.stock import Stock

logger = logging.getLogger(__name__)

# 进程内缓存：{code: (fingerprint, result_dict)}
# fingerprint = 最近 5 行关键字段的内容 hash，任何一个字段变化都失效
_ANALYSIS_CACHE: dict[str, tuple[str, dict]] = {}
_CACHE_MAX_SIZE = 200
_FINGERPRINT_TAIL = 5  # 只 hash 最后 N 行；老数据只在回填后短暂不一致，风险可控


def _fingerprint(df: pd.DataFrame) -> str:
    """基于最近 N 行内容的 hash。所有 OHLCV/turnover/pct_chg 变化都会改指纹。"""
    tail = df.tail(_FINGERPRINT_TAIL)[
        ["trade_date", "open", "high", "low", "close",
         "volume", "amount", "turnover", "pct_chg"]
    ]
    # 行数一起塞入以区分"最后 5 行相同但历史行数不同"的极端情况
    payload = f"{len(df)}|{tail.to_csv(index=False, header=False, na_rep='NULL')}"
    return hashlib.sha1(payload.encode()).hexdigest()


def load_kline_df(session: Session, code: str, days: int = 500) -> pd.DataFrame:
    end = date.today()
    start = end - timedelta(days=days * 2)
    stmt = (
        select(KlineDaily)
        .where(KlineDaily.code == code, KlineDaily.trade_date >= start)
        .order_by(KlineDaily.trade_date.asc())
    )
    rows = list(session.exec(stmt))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "trade_date": r.trade_date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "amount": r.amount,
                "turnover": r.turnover,
                "pct_chg": r.pct_chg,
            }
            for r in rows
        ]
    )


def analyze(session: Session, code: str) -> dict:
    df = load_kline_df(session, code)
    stock = session.get(Stock, code)
    if df.empty:
        return {
            "code": code,
            "name": stock.name if stock else None,
            "empty": True,
            "message": "本地无数据，请先同步",
        }

    fingerprint = _fingerprint(df)
    cached = _ANALYSIS_CACHE.get(code)
    if cached and cached[0] == fingerprint:
        logger.debug("analyze cache hit for %s", code)
        return cached[1]

    indicators = compute_all(df)
    series = build_chart_series(df)
    signals = scan_signals(indicators)
    result = {
        "code": code,
        "name": stock.name if stock else None,
        "market": stock.market if stock else None,
        "indicators": indicators,
        "series": series,
        "signals": signals,
    }

    _ANALYSIS_CACHE[code] = (fingerprint, result)
    # 粗糙 LRU：超过阈值随便清一半
    if len(_ANALYSIS_CACHE) > _CACHE_MAX_SIZE:
        for k in list(_ANALYSIS_CACHE.keys())[: _CACHE_MAX_SIZE // 2]:
            _ANALYSIS_CACHE.pop(k, None)

    return result


def invalidate_analysis_cache(code: str | None = None) -> None:
    """通常不需要手动调 —— 指纹是内容 hash，K 线一变自动失效。保留仅为特殊场景（如
    调试、跨进程外部改库后强制刷新单进程缓存）。"""
    if code is None:
        _ANALYSIS_CACHE.clear()
    else:
        _ANALYSIS_CACHE.pop(code, None)


def build_ai_input(session: Session, code: str) -> tuple[dict, dict] | None:
    """给 AI 的输入：股票信息 + { 'daily': 日线指标, 'weekly': 周线指标, 'market': 大盘上下文 }。"""
    df = load_kline_df(session, code)
    if df.empty:
        return None
    stock = session.get(Stock, code)
    stock_info = {
        "code": code,
        "name": stock.name if stock else "-",
        "market": stock.market if stock else "-",
    }
    daily_ind = compute_all(df)
    weekly_df = aggregate_weekly(df)
    weekly_ind = compute_all(weekly_df) if not weekly_df.empty else {"empty": True}

    # 大盘上下文（无则为空 dict，不阻塞主流程）
    try:
        from app.services.market_service import get_market_context

        market = get_market_context(session)
    except Exception:  # noqa: BLE001
        market = {}

    return stock_info, {
        "daily": daily_ind,
        "weekly": weekly_ind,
        "market": market,
        "as_of_date": daily_ind.get("as_of_date"),
    }

