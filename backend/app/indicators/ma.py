"""均线系统：MA5/10/20/60/120/250 + 排列形态 + 序列输出（供前端叠加）。"""
from __future__ import annotations

import pandas as pd

MA_PERIODS = (5, 10, 20, 60, 120, 250)


def compute_ma_series(df: pd.DataFrame) -> dict[str, pd.Series]:
    """返回每根 MA 的完整时间序列，用于前端叠加线。"""
    close = df["close"]
    return {f"ma{p}": close.rolling(p).mean() for p in MA_PERIODS}


def compute_ma(df: pd.DataFrame) -> dict:
    """最新一根 K 线的 MA 值 + 排列形态。"""
    series = compute_ma_series(df)
    latest: dict = {}
    for p in MA_PERIODS:
        s = series[f"ma{p}"]
        val = s.iloc[-1] if len(s) and pd.notna(s.iloc[-1]) else None
        latest[f"ma{p}"] = float(val) if val is not None else None
    latest["arrangement"] = _classify_arrangement(latest)
    latest["ma5_ma10_cross"] = _detect_cross(series["ma5"], series["ma10"])
    latest["ma5_ma20_cross"] = _detect_cross(series["ma5"], series["ma20"])
    return latest


def _classify_arrangement(ma: dict) -> str:
    seq = [ma.get(f"ma{p}") for p in (5, 10, 20, 60)]
    if any(v is None for v in seq):
        return "insufficient"
    if seq[0] > seq[1] > seq[2] > seq[3]:
        return "bullish"
    if seq[0] < seq[1] < seq[2] < seq[3]:
        return "bearish"
    return "tangled"


def _detect_cross(fast: pd.Series, slow: pd.Series) -> str | None:
    """检测最近一根是否发生金叉/死叉。"""
    if len(fast) < 2 or len(slow) < 2:
        return None
    f0, f1 = fast.iloc[-2], fast.iloc[-1]
    s0, s1 = slow.iloc[-2], slow.iloc[-1]
    if any(pd.isna(v) for v in (f0, f1, s0, s1)):
        return None
    if f0 <= s0 and f1 > s1:
        return "golden"
    if f0 >= s0 and f1 < s1:
        return "death"
    return None
