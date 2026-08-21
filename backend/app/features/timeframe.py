"""打分/趋势算法的周期层：把算法（bar 级运算）与 K 线原始粒度（日/周/月）解耦。

stock_scorer / trend_judge 全部以"bar"做单位运算，不感知 trade_date 是日还是周；
本模块只负责把数据源的日线 DataFrame resample 成目标周期，让上层 scan/query 通过
timeframe 参数选择输入哪种 bar。

设计：注册表式（REGISTRY），后续加月度/小时只改这里，上层不动。
"""
from __future__ import annotations

from typing import Literal

import pandas as pd

Timeframe = Literal["daily", "weekly"]

# 波动率尺度系数：weekly sigma / daily sigma 实测中位数倍数（2026-08-21 全 A 200 只样本实测 2.60，取 2.56 为折中）
# 用途：把 weekly sigma 折回"日等效"再喂给 _tri() 锚点，让打分分布跨周期对齐。
# 节奏（ma5_stay_days）实测 daily p50=3.95 vs weekly p50=3.97（bar 单位），基本不变，不需要折换。
# 测法：scripts/calibrate_timeframe.py（每次大改最好再跑一次校准）
SIGMA_SCALE: dict[Timeframe, float] = {
    "daily": 1.0,
    "weekly": 2.56,
}


def resample_to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """日线 DataFrame → 周五收盘周线（Wall St 风格 W-FRI 锚点）。

    聚合规则：open=首、high=最大、low=最小、close=尾、volume/amount=求和。
    turnover / pct_chg 由打分/judge 内部从 close 派生，不在此重复聚合（pct_change 关系
    会随 resample 漂移，留给下游 compute_indicator_cache 重算）。
    """
    if df is None or df.empty:
        return df
    if "trade_date" not in df.columns:
        return df
    d = df.copy()
    d["trade_date"] = pd.to_datetime(d["trade_date"])
    d = d.set_index("trade_date")
    weekly = d.resample("W-FRI").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "amount": "sum",
    }).dropna(subset=["close"])
    weekly = weekly.reset_index()
    return weekly[["trade_date", "open", "high", "low", "close", "volume", "amount"]]


def to_bars(daily_df: pd.DataFrame, timeframe: Timeframe = "daily") -> pd.DataFrame:
    """按目标周期返回 bar DataFrame：daily→原样，weekly→周五收盘 resample。

    后续加 monthly/其他周期：只需在这里加一个分支。
    """
    if daily_df is None or daily_df.empty:
        return daily_df
    if timeframe == "daily":
        return daily_df
    if timeframe == "weekly":
        return resample_to_weekly(daily_df)
    raise ValueError(f"unsupported timeframe: {timeframe}")
