"""风险与波动率指标。

- ATR：Average True Range，用来给出止损位参考
- 历史波动率：年化标准差
- 最大回撤：滚动窗口内最大回撤
- 阶段波动：近 20 日日内振幅均值
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd


def compute_risk(df: pd.DataFrame) -> dict:
    """输入日线 DataFrame（trade_date/open/high/low/close 齐全），输出风险度量。"""
    if df is None or df.empty or len(df) < 15:
        return {
            "atr14": None,
            "atr_pct": None,
            "hist_vol_20d": None,
            "max_drawdown_60d": None,
            "avg_range_20d": None,
            "stop_loss_hint": None,
        }

    high = df["high"].astype(float)
    low = df["low"].astype(float)
    close = df["close"].astype(float)
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    atr14 = tr.ewm(alpha=1 / 14, adjust=False).mean().iloc[-1]
    latest_close = float(close.iloc[-1])
    atr_pct = round(atr14 / latest_close * 100, 2) if latest_close else None
    stop_loss_hint = round(latest_close - 2 * atr14, 2) if latest_close else None  # 2 倍 ATR 常见止损

    # 20 日历史波动率（年化）
    log_ret = np.log(close / close.shift(1)).dropna()
    if len(log_ret) >= 20:
        vol_20 = float(log_ret.tail(20).std() * math.sqrt(252) * 100)
    else:
        vol_20 = None

    # 60 日最大回撤
    window = close.tail(60) if len(close) >= 60 else close
    if len(window) >= 2:
        rolling_max = window.cummax()
        drawdown = (window - rolling_max) / rolling_max
        max_dd = float(drawdown.min() * 100)  # 负数
    else:
        max_dd = None

    # 20 日平均振幅
    if len(df) >= 20:
        recent = df.tail(20)
        prev_c = recent["close"].shift(1).fillna(recent["open"])
        amp = (recent["high"] - recent["low"]) / prev_c * 100
        avg_range = round(float(amp.mean()), 2)
    else:
        avg_range = None

    return {
        "atr14": round(float(atr14), 2),
        "atr_pct": atr_pct,
        "hist_vol_20d": round(vol_20, 1) if vol_20 is not None else None,
        "max_drawdown_60d": round(max_dd, 2) if max_dd is not None else None,
        "avg_range_20d": avg_range,
        "stop_loss_hint": stop_loss_hint,
    }
