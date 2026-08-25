"""金叉延续性单元测试：反复横跳检测 + 金叉后涨幅降级。"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.features.scoring import _golden_continuation, _golden_life_score, _post_golden_gain


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


def test_whipsaw_short_intervals_low_score():
    """金叉后 3 天就再次交叉（快速再次交叉）→ 反复横跳，分数低。"""
    signals = [(10, "golden"), (13, "death"), (16, "golden"), (19, "death")]
    assert _golden_life_score(signals) < 30


def test_whipsaw_long_intervals_high_score():
    """金叉寿命长、无快速再次交叉 → 金叉延续好，分数高。"""
    signals = [(10, "golden"), (50, "death"), (100, "golden")]
    assert _golden_life_score(signals) > 60


def test_whipsaw_no_or_single_signal_neutral():
    assert _golden_life_score([]) == 60.0
    # 只有金叉无后续死叉：当前仍在金叉延续中，高分
    assert _golden_life_score([(5, "golden")]) == 80.0


def test_post_golden_gain_insufficient_neutral():
    """无金叉信号 → 延续涨幅回退中性 50。"""
    closes = list(np.linspace(10, 20, 60))
    assert _post_golden_gain(pd.Series(closes), []) == 50.0


def test_frequent_crossing_penalizes_golden_continuation():
    """锯齿反复横跳序列 → 反复横跳、快速再次交叉，金叉延续分低。"""
    closes = [10.0 + np.sin(i / 2) * 0.3 for i in range(300)]
    sig = _golden_continuation(_mk_df(closes))
    assert sig["signal_count"] > 8
    assert sig["whipsaw_score"] < 40
