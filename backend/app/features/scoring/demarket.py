"""去市场因素模块（去 beta / 去普涨普跌）。

独立于打分引擎，与打分计算解耦：本模块只负责"提供市场基准 + 按周期对齐求市场涨幅"，
打分引擎在算完历史金叉涨幅后，调用这里的超额计算，把绝对涨幅改成相对市场的超额涨幅。

设计意图：后续扩展（行业中性化、CAPM β 回归、横截面 z-score）都放本模块，
打分引擎的改动只限"加一个调用步骤"，互不耦合。

当前实现：仅"去除上证指数涨幅"（超额收益法，业界最简剥离方式）。
基准 = sh000001（上证指数），进程内缓存。
"""
from __future__ import annotations

import pandas as pd

from app.db import engine
from app.models.kline import KlineDaily
from sqlmodel import Session, select

# 市场基准代码：上证指数（当前只用上证，后续可加深成/沪深300 或按票所属市场选）
MARKET_CODE = "sh000001"

# 进程内缓存，避免每次打分都查库（扫描 244 只时省大量 IO）
_market_df: pd.DataFrame | None = None


def load_market() -> pd.DataFrame:
    """上证指数日线：index=trade_date(Timestamp)，列 market_close。进程内缓存。"""
    global _market_df
    if _market_df is not None:
        return _market_df
    with Session(engine) as s:
        rows = s.exec(
            select(KlineDaily.trade_date, KlineDaily.close)
            .where(KlineDaily.code == MARKET_CODE)
            .order_by(KlineDaily.trade_date)
        ).all()
    df = pd.DataFrame(
        {"trade_date": [pd.Timestamp(r[0]) for r in rows],
         "market_close": [float(r[1]) for r in rows]}
    ).set_index("trade_date").sort_index()
    _market_df = df
    return df


def market_gain(dates, base_idx: int, end_idx: int, market: pd.DataFrame | None = None) -> float | None:
    """区间 [dates[base_idx-1], dates[end_idx]] 的上证涨幅（基准=base_idx-1 日收盘）。

    base_idx：金叉/信号的 index（基准用前一日收盘，同 _post_golden_gain 口径）。
    end_idx：区间结束 index（周期最高收盘日 / 死叉日）。
    返回小数（0.1 = 涨 10%）；市场数据无法对齐（缺失/零价）返回 None。
    无未来函数：只用 <= 区间末日期的市场数据（asof）。
    """
    if market is None:
        market = load_market()
    base_date = dates[base_idx - 1] if base_idx > 0 else dates[base_idx]
    end_date = dates[end_idx]
    try:
        base_m = market["market_close"].asof(pd.Timestamp(base_date))
        end_m = market["market_close"].asof(pd.Timestamp(end_date))
    except (KeyError, ValueError):
        return None
    if base_m is None or end_m is None or pd.isna(base_m) or pd.isna(end_m) or base_m <= 0:
        return None
    return float(end_m) / float(base_m) - 1


def excess_gain(gain_pct: float, dates, base_idx: int, end_idx: int,
                market: pd.DataFrame | None = None) -> float:
    """超额涨幅 = 个股涨幅 − 同期上证涨幅。

    gain_pct 为小数（0.1 = 涨 10%）。市场对齐失败时退回原涨幅（不削足适履）。
    """
    mg = market_gain(dates, base_idx, end_idx, market)
    if mg is None:
        return gain_pct
    return gain_pct - mg
