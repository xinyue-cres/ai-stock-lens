"""多股对比：纯计算函数（无 DB 依赖，方便单测）。"""
from __future__ import annotations

import pandas as pd


def normalize(series: pd.Series) -> list[float]:
    """把序列按首值归一为 100。"""
    if series.empty:
        return []
    base = float(series.iloc[0])
    if base == 0:
        return [100.0 for _ in series]
    return [round(float(v) / base * 100, 2) for v in series]


def pct_change(series: pd.Series, n: int) -> float | None:
    """n 日累计涨幅（%），长度不足返回 None。"""
    if len(series) <= n:
        return None
    base = series.iloc[-(n + 1)]
    if pd.isna(base) or base == 0:
        return None
    return round((series.iloc[-1] - base) / base * 100, 2)
