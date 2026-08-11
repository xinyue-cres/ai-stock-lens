"""打分引擎单元测试：数据不足、归一化边界、综合分权重、股息单位。"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.features.stock_scorer import _norm, _tri, score_stock


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


def test_insufficient_data_returns_none():
    assert score_stock(_mk_df(list(np.linspace(10, 12, 50)))) is None


def test_norm_and_tri_boundaries():
    assert _norm(5, 10, 20) == 0.0
    assert _norm(15, 10, 20) == 0.5
    assert _norm(25, 10, 20) == 1.0
    assert _tri(0.03, 0.015, 0.03, 0.045) == 1.0  # 峰值
    assert _tri(0.05, 0.015, 0.03, 0.045) == 0.0  # 超上限


def test_uptrend_scores_high_on_signal():
    """金叉后一路延续：跌后急涨形成金叉且长期不死叉，金叉延续分应高。"""
    closes = list(np.linspace(30, 10, 150)) + list(np.linspace(10, 30, 150))
    sc = score_stock(_mk_df(closes))
    assert sc is not None
    assert sc["signal_score"] > 60


def test_whipsaw_penalizes_signal_score():
    """锯齿反复横跳：信号多、延续分显著低于单调上升。"""
    closes = [10.0 + np.sin(i / 2) * 0.3 for i in range(300)]
    sc = score_stock(_mk_df(closes))
    assert sc is not None
    # 锚点 24% 校准后绝对分数整体上移（横跳 56.6 / 单调 74.4），不再用硬编码 <50，
    # 改为相对比较"横跳显著低于单调"，更反映"被惩罚"的意图
    up = list(np.linspace(30, 10, 150)) + list(np.linspace(10, 30, 150))
    sc_up = score_stock(_mk_df(up))
    assert sc_up is not None
    assert sc["signal_score"] < sc_up["signal_score"] - 10


def test_dividend_uses_percent_unit():
    """股息率按百分数（6.5 = 6.5%）→ 满分 100；ETF 无股息 → 中性 50。"""
    closes = list(np.linspace(10, 30, 300))
    df = _mk_df(closes)
    sc = score_stock(df, dividend_yield=6.5)
    assert sc["dividend_score"] == 100.0
    sc2 = score_stock(df, dividend_yield=None, is_fund=True)
    assert sc2["dividend_score"] == 50.0


def test_total_score_is_weighted_sum():
    closes = list(np.linspace(10, 30, 300))
    sc = score_stock(_mk_df(closes), dividend_yield=3.0)
    expected = (0.70 * sc["signal_score"] + 0.20 * sc["band_score"]
                + 0.10 * sc["dividend_score"])
    assert abs(sc["total_score"] - expected) < 0.5
