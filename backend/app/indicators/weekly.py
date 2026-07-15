"""周线聚合：从日线 DataFrame 生成周线 DataFrame。"""
from __future__ import annotations

import pandas as pd


def aggregate_weekly(df_daily: pd.DataFrame) -> pd.DataFrame:
    """把日线聚合为周线（周五收盘为周末）。

    输入 columns: [trade_date, open, high, low, close, volume, amount, turnover, pct_chg]
    输出 columns 同上，trade_date 为该周最后一个交易日
    """
    if df_daily is None or df_daily.empty:
        return pd.DataFrame(columns=df_daily.columns if df_daily is not None else [])

    df = df_daily.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    df = df.sort_values("trade_date").set_index("trade_date")

    # 按 ISO 周（周一到周日）聚合
    week_key = df.index.to_series().dt.to_period("W-SUN")

    agg = df.groupby(week_key).agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        amount=("amount", "sum"),
        trade_date=("close", lambda _s: df.loc[_s.index].index.max()),
    )
    agg["pct_chg"] = agg["close"].pct_change().fillna(0) * 100
    agg["turnover"] = None
    agg = agg.reset_index(drop=True)
    agg["trade_date"] = pd.to_datetime(agg["trade_date"]).dt.date
    return agg[
        ["trade_date", "open", "high", "low", "close", "volume", "amount", "turnover", "pct_chg"]
    ]
