"""趋势判断单元测试：金叉驱动决策 + 数据不足。

合成 K 线的 MACD 金叉态窗口很窄（刚金叉、价格贴中轨），单调序列难以稳定命中
"金叉 + %B 适中 = 可入手"；因此这里覆盖可可靠构造的分支：死叉态（signal 高→观望
/低→回避）、金叉态贴上轨（→过热）、数据不足。
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.features.trend_judge import judge_trend


def _mk_df(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    base = date(2024, 1, 1)
    return pd.DataFrame([
        {
            "trade_date": base + timedelta(days=i),
            "open": c,
            "high": c * 1.01,
            "low": c * 0.99,
            "close": c,
            "volume": 1_000_000,
            "amount": c * 1_000_000,
            "turnover": 1.5,
            "pct_chg": 0.0 if i == 0 else (c / closes[i - 1] - 1) * 100,
        }
        for i, c in enumerate(closes)
    ])


def test_insufficient_data():
    # <60 根，MACD EMA26 未预热
    r = judge_trend(_mk_df(list(np.linspace(10, 12, 50))))
    assert r["trend_stage"] == "insufficient"
    assert r["can_entry"] is False


def test_downtrend_deadcross_low_signal():
    """死叉态 + 历史金叉延续差 → 下跌趋势回避。"""
    closes = list(np.linspace(10, 20, 80)) + list(np.linspace(20, 14, 70))
    r = judge_trend(_mk_df(closes), signal_score=30)
    assert r["trend_stage"] == "downtrend"
    assert not r["can_entry"]


def test_range_deadcross_high_signal():
    """死叉态但历史金叉延续可靠 → 观望，等下次金叉。"""
    closes = list(np.linspace(10, 20, 80)) + list(np.linspace(20, 14, 70))
    r = judge_trend(_mk_df(closes), signal_score=85)
    assert r["trend_stage"] == "range"


def test_overheat_golden_touches_upper():
    """金叉态但贴上轨（%B 高）→ 短期过热，等回踩。"""
    closes = list(np.linspace(20, 10, 80)) + list(np.linspace(10, 14, 70))
    r = judge_trend(_mk_df(closes), signal_score=85)
    assert r["trend_stage"] == "overheat"
    assert r["indicators"]["pct_b"] is not None
    assert r["indicators"]["pct_b"] > 0.85
