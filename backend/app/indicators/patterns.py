"""价格形态识别。"""
from __future__ import annotations

import pandas as pd


def compute_patterns(df: pd.DataFrame) -> list[str]:
    if len(df) < 21:
        return []
    patterns: list[str] = []
    close = df["close"]
    high = df["high"]
    low = df["low"]

    latest_close = float(close.iloc[-1])
    prev_close = float(close.iloc[-2])
    latest_high = float(high.iloc[-1])
    latest_low = float(low.iloc[-1])

    high_20 = float(high.iloc[-21:-1].max())
    low_20 = float(low.iloc[-21:-1].min())
    high_60 = float(high.iloc[-61:-1].max()) if len(df) >= 61 else None
    low_60 = float(low.iloc[-61:-1].min()) if len(df) >= 61 else None

    if latest_close > high_20:
        patterns.append("突破 20 日新高")
    if latest_close < low_20:
        patterns.append("跌破 20 日新低")
    if high_60 is not None and latest_close > high_60:
        patterns.append("突破 60 日新高")
    if low_60 is not None and latest_close < low_60:
        patterns.append("跌破 60 日新低")

    if len(df) >= 6:
        ma5 = float(close.iloc[-6:-1].mean())
        prev_ma5 = float(close.iloc[-7:-2].mean()) if len(df) >= 7 else None
        if prev_close < ma5 and latest_close > ma5:
            patterns.append("上穿 5 日均线")
        elif prev_close > ma5 and latest_close < ma5:
            patterns.append("下穿 5 日均线")
        _ = prev_ma5  # 预留位

    body = abs(latest_close - float(df["open"].iloc[-1]))
    total_range = latest_high - latest_low
    if total_range > 0 and body / total_range < 0.2:
        upper_shadow = latest_high - max(latest_close, float(df["open"].iloc[-1]))
        lower_shadow = min(latest_close, float(df["open"].iloc[-1])) - latest_low
        if upper_shadow > body * 2 and lower_shadow < body:
            patterns.append("上影线较长（阻力显现）")
        elif lower_shadow > body * 2 and upper_shadow < body:
            patterns.append("下影线较长（支撑显现）")

    return patterns
