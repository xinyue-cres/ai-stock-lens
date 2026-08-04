"""MACD（指数平滑异同移动平均线）。

标准参数：DIF = EMA12 − EMA26，DEA = EMA(DIF, 9)；
金叉 = DIF 上穿 DEA，死叉 = DIF 下穿 DEA。

本模块提供全历史序列 + 交叉信号列表 + 当前斜率，供打分引擎
（features/stock_scorer）与趋势判断（features/trend_judge）共用；
oscillators.compute_macd 的快照也基于 macd_series 计算 DIF/DEA——
同一指标只有一份实现。
"""
from __future__ import annotations

import pandas as pd

_DEFAULT_FAST = 12
_DEFAULT_SLOW = 26
_DEFAULT_SIGNAL = 9


def macd_series(
    close: pd.Series,
    fast: int = _DEFAULT_FAST,
    slow: int = _DEFAULT_SLOW,
    signal: int = _DEFAULT_SIGNAL,
) -> tuple[pd.Series, pd.Series, list[tuple[int, str]]]:
    """MACD 全序列：返回 (dif, dea, signals)。

    - dif = EMA(fast) − EMA(slow)；dea = EMA(dif, signal)；
    - signals = [(索引, 'golden' | 'death')]，按时间升序，为 DIF 上穿/下穿 DEA
      的交叉点（用于统计历史金叉/死叉表现，而非只看当前快照）。
    """
    dif = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    dea = dif.ewm(span=signal, adjust=False).mean()
    signals: list[tuple[int, str]] = []
    for i in range(1, len(close)):
        d0, d1 = dif.iloc[i - 1], dif.iloc[i]
        e0, e1 = dea.iloc[i - 1], dea.iloc[i]
        if any(pd.isna(v) for v in (d0, d1, e0, e1)):
            continue
        if d0 <= e0 and d1 > e1:
            signals.append((i, "golden"))
        elif d0 >= e0 and d1 < e1:
            signals.append((i, "death"))
    return dif, dea, signals


def dif_slope(dif: pd.Series) -> float | None:
    """DIF 当前斜率：当日 DIF −（昨日 + 前日）/2。

    比单日差分平滑（过滤整体上升中的单日回调噪声，方向不频繁翻转），
    又比 3/5 日窗口即时（参考窗口仅 2 天）。仅作展示参考，不参与评分。
    数据不足返回 None。
    """
    if len(dif) >= 3 and pd.notna(dif.iloc[-1]) and pd.notna(dif.iloc[-2]) and pd.notna(dif.iloc[-3]):
        return round(float(dif.iloc[-1] - (dif.iloc[-2] + dif.iloc[-3]) / 2), 6)
    return None


def is_golden(dif: pd.Series, dea: pd.Series) -> bool:
    """当前是否为金叉态（DIF > DEA）。数据不足按死叉态处理。"""
    if len(dif) > 0 and pd.notna(dif.iloc[-1]) and pd.notna(dea.iloc[-1]):
        return bool(dif.iloc[-1] > dea.iloc[-1])
    return False
