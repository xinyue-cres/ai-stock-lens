"""ADX 单元测试：趋势段高、盘整段低、数据不足返回 None。"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.indicators.adx import compute_adx


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


def test_adx_high_on_smooth_uptrend():
    """平滑上升趋势：ADX 应显著高于 25（强单边）。"""
    closes = list(np.linspace(10, 30, 200))
    result = compute_adx(_mk_df(closes))
    assert result["adx"] is not None
    assert result["adx"] > 25


def test_adx_low_on_noise():
    """纯随机噪音：ADX 应低于 20（无趋势）。"""
    np.random.seed(42)
    closes = list(10 + np.random.randn(200) * 0.3)
    result = compute_adx(_mk_df(closes))
    assert result["adx"] is not None
    assert result["adx"] < 20


def test_adx_returns_none_on_short_data():
    result = compute_adx(_mk_df([10.0] * 20))
    assert result["adx"] is None
    assert result["plus_di"] is None
