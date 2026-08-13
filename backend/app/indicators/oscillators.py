"""振荡/趋势指标：MACD / KDJ / RSI / BOLL。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.indicators.macd import macd_series


def compute_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    close = df["close"]
    # DIF/DEA 全序列复用 macd_series（同一指标只有一份实现）
    dif, dea, _signals = macd_series(close, fast, slow, signal)
    hist = (dif - dea) * 2

    # cross 只判断"最后两根是否刚好交叉"（快照，非历史上最近一次交叉）
    cross = None
    if len(dif) >= 2 and len(dea) >= 2:
        d0, d1 = dif.iloc[-2], dif.iloc[-1]
        e0, e1 = dea.iloc[-2], dea.iloc[-1]
        if pd.notna(d0) and pd.notna(d1) and pd.notna(e0) and pd.notna(e1):
            if d0 <= e0 and d1 > e1:
                cross = "golden"
            elif d0 >= e0 and d1 < e1:
                cross = "death"

    return {
        "dif": _last_float(dif),
        "dea": _last_float(dea),
        "hist": _last_float(hist),
        "cross": cross,
    }


def compute_kdj(df: pd.DataFrame, n: int = 9) -> dict:
    """经典 KDJ（M1=3, M2=3）。"""
    low_n = df["low"].rolling(n).min()
    high_n = df["high"].rolling(n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n) * 100
    rsv = rsv.replace([np.inf, -np.inf], np.nan).fillna(50)
    k = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    d = k.ewm(alpha=1 / 3, adjust=False).mean()
    j = 3 * k - 2 * d
    return {
        "k": _last_float(k),
        "d": _last_float(d),
        "j": _last_float(j),
        "signal": _classify_kdj(_last_float(k), _last_float(d), _last_float(j)),
    }


def _classify_kdj(k, d, j) -> str | None:
    if k is None or d is None or j is None:
        return None
    if j < 0 or (k < 20 and d < 20):
        return "oversold"
    if j > 100 or (k > 80 and d > 80):
        return "overbought"
    return "neutral"


def compute_rsi(df: pd.DataFrame) -> dict:
    close = df["close"]
    # diff/clip 只算一次，三个窗口(6/12/24)复用 up/down——原来每个窗口各自重算
    # diff+clip（工作台 compute_all 最大热点）。只取末值，不需要多份全序列。
    delta = close.diff()
    up = delta.clip(lower=0)
    down = -delta.clip(upper=0)
    return {
        "rsi6": _last_float(_rsi_from_updown(up, down, 6)),
        "rsi12": _last_float(_rsi_from_updown(up, down, 12)),
        "rsi24": _last_float(_rsi_from_updown(up, down, 24)),
    }


def _rsi_from_updown(up: pd.Series, down: pd.Series, n: int) -> pd.Series:
    avg_up = up.ewm(alpha=1 / n, adjust=False).mean()
    avg_down = down.ewm(alpha=1 / n, adjust=False).mean()
    rs = avg_up / avg_down.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return rsi.fillna(50)


def compute_boll(df: pd.DataFrame, n: int = 20, k: float = 2.0) -> dict:
    close = df["close"]
    middle = close.rolling(n).mean()
    std = close.rolling(n).std()
    upper = middle + k * std
    lower = middle - k * std

    latest_close = float(close.iloc[-1])
    u = _last_float(upper)
    l = _last_float(lower)
    m = _last_float(middle)
    position: str | None = None
    if u is not None and l is not None:
        if latest_close >= u:
            position = "above_upper"
        elif latest_close <= l:
            position = "below_lower"
        elif m is not None:
            position = "above_middle" if latest_close >= m else "below_middle"

    # %B + 带宽：价格在带内位置 + 波动空间（趋势判断衡量"上方空间"用）
    pct_b = None
    bandwidth = None
    if u is not None and l is not None and m not in (None, 0):
        if u != l:
            pct_b = round((latest_close - l) / (u - l), 4)
        bandwidth = round((u - l) / m, 4)

    return {"upper": u, "middle": m, "lower": l, "position": position, "pct_b": pct_b, "bandwidth": bandwidth}


def compute_oscillators(df: pd.DataFrame) -> dict:
    return {
        "macd": compute_macd(df),
        "kdj": compute_kdj(df),
        "rsi": compute_rsi(df),
        "boll": compute_boll(df),
    }


def _last_float(s: pd.Series) -> float | None:
    if s is None or len(s) == 0:
        return None
    v = s.iloc[-1]
    if pd.isna(v):
        return None
    return float(v)
