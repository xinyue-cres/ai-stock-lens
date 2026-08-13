"""ADX（Average Directional Index，平均趋向指数）。

衡量趋势强度：ADX 高（>25）代表趋势强且单边，低（<20）代表震荡盘整。
+DI / −DI 的方向差给出多空倾向（+DI > −DI 偏多）。

实现：Wilders RMA 平滑（ewm alpha=1/n, adjust=False），与 risk.compute_risk 的
ATR 平滑口径一致。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_PERIOD = 14
_MIN_ROWS = 2 * _PERIOD + 5  # 平滑需要预热，太少没有意义


def compute_adx(df: pd.DataFrame) -> dict:
    """输入日线 DataFrame（trade_date/high/low/close 齐全，升序），输出 ADX 快照。

    返回 {adx, plus_di, minus_di}；数据不足返回 {adx: None, plus_di: None, minus_di: None}。
    """
    empty = {"adx": None, "plus_di": None, "minus_di": None}
    if df is None or df.empty or len(df) < _MIN_ROWS:
        return empty

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)

    prev_high = high.shift(1)
    prev_low = low.shift(1)
    prev_close = close.shift(1)

    up_move = high - prev_high
    down_move = prev_low - low

    plus_dm = pd.Series(np.where(
        (up_move > down_move) & (up_move > 0), up_move, 0.0
    ), index=df.index)
    minus_dm = pd.Series(np.where(
        (down_move > up_move) & (down_move > 0), down_move, 0.0
    ), index=df.index)

    # True Range：三元素逐点取最大（同 risk.compute_risk 口径；numpy 比 pd.concat+max 快）。
    # 用 np.fmax（忽略 NaN）复刻 pandas max 的 skipna 语义：首根 prev_close 为 NaN 时仍取 high-low。
    tr = pd.Series(
        np.fmax.reduce([
            (high - low).to_numpy(),
            (high - prev_close).abs().to_numpy(),
            (low - prev_close).abs().to_numpy(),
        ]),
        index=df.index,
    )

    tr = tr.astype(float)
    plus_dm = plus_dm.astype(float)
    minus_dm = minus_dm.astype(float)

    atr = tr.ewm(alpha=1 / _PERIOD, adjust=False).mean()
    plus_di = 100 * plus_dm.ewm(alpha=1 / _PERIOD, adjust=False).mean() / atr
    minus_di = 100 * minus_dm.ewm(alpha=1 / _PERIOD, adjust=False).mean() / atr

    di_sum = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / di_sum
    adx = dx.ewm(alpha=1 / _PERIOD, adjust=False).mean()

    last_adx = adx.iloc[-1]
    last_plus = plus_di.iloc[-1]
    last_minus = minus_di.iloc[-1]

    if any(pd.isna(v) for v in (last_adx, last_plus, last_minus)):
        return empty

    return {
        "adx": round(float(last_adx), 2),
        "plus_di": round(float(last_plus), 2),
        "minus_di": round(float(last_minus), 2),
    }
