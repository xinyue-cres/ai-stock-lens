"""量能系统：量比、放缩量识别。

- 量比 = 当日成交量 / 过去 N 日平均量
- 换手率 直接从数据源取
- 量能形态：放量突破 / 放量下跌 / 缩量整理 等
"""
from __future__ import annotations

import pandas as pd


def compute_volume(df: pd.DataFrame, avg_window: int = 5) -> dict:
    if len(df) < 2:
        return {"turnover": None, "vol_ratio": None, "volume_pattern": None}

    volume = df["volume"]
    latest_vol = float(volume.iloc[-1])
    avg = float(volume.iloc[-(avg_window + 1) : -1].mean()) if len(volume) > avg_window else None
    vol_ratio = latest_vol / avg if avg and avg > 0 else None

    turnover = df["turnover"].iloc[-1] if "turnover" in df.columns else None
    turnover = float(turnover) if pd.notna(turnover) else None

    latest_pct = df["pct_chg"].iloc[-1] if "pct_chg" in df.columns else None
    latest_pct = float(latest_pct) if pd.notna(latest_pct) else 0.0

    pattern = _classify_volume(vol_ratio, latest_pct)

    return {
        "turnover": turnover,
        "vol_ratio": round(vol_ratio, 2) if vol_ratio else None,
        "volume_pattern": pattern,
    }


def _classify_volume(vol_ratio: float | None, pct_chg: float) -> str | None:
    if vol_ratio is None:
        return None
    if vol_ratio >= 2.0:
        if pct_chg >= 3:
            return "big_volume_up"       # 放量上涨
        if pct_chg <= -3:
            return "big_volume_down"     # 放量下跌
        return "big_volume_flat"          # 放量滞涨
    if vol_ratio <= 0.6:
        return "shrink_volume"            # 缩量整理
    return "normal"
