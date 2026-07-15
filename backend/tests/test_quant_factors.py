"""quant_factors 单元测试：核心因子计算正确性 + 数据不足场景。"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.features.quant_factors import compute_quant_features


def _mk_df(closes: list[float]) -> pd.DataFrame:
    """给一串 close 造一个合法 df，其他字段用简单规则填充。"""
    n = len(closes)
    base = date(2024, 1, 1)
    rows = []
    for i, c in enumerate(closes):
        rows.append({
            "trade_date": base + timedelta(days=i),
            "open": c,
            "high": c * 1.02,
            "low": c * 0.98,
            "close": c,
            "volume": 1_000_000 + i * 1000,
            "amount": c * (1_000_000 + i * 1000),
            "turnover": 1.5 + (i % 10) * 0.1,
            "pct_chg": 0.0 if i == 0 else (c / closes[i - 1] - 1) * 100,
        })
    return pd.DataFrame(rows)


def test_empty_df_returns_empty_flag():
    result = compute_quant_features(pd.DataFrame())
    assert result == {"empty": True}


def test_momentum_computes_correct_returns():
    # 简单等差递增：close 从 10 涨到 30，20 日累计约 +100%
    closes = list(np.linspace(10, 30, 130))
    result = compute_quant_features(_mk_df(closes))
    m = result["momentum"]
    # return_20d = (close[-1] - close[-21]) / close[-21]
    expected = (closes[-1] - closes[-21]) / closes[-21]
    assert abs(m["return_20d"] - expected) < 1e-4
    assert m["return_60d"] is not None
    assert m["return_120d"] is not None


def test_momentum_returns_none_when_data_insufficient():
    closes = list(range(10, 30))  # 只有 20 行
    result = compute_quant_features(_mk_df(closes))
    m = result["momentum"]
    assert m["return_60d"] is None
    assert m["return_120d"] is None


def test_volatility_atr_ratio_positive():
    # 随机波动 200 行
    np.random.seed(42)
    closes = list(10 + np.cumsum(np.random.randn(200) * 0.1))
    result = compute_quant_features(_mk_df(closes))
    v = result["volatility"]
    assert v["sigma_20d"] is not None and v["sigma_20d"] > 0
    assert v["atr_ratio_14d"] is not None and v["atr_ratio_14d"] > 0


def test_price_position_at_top_and_bottom():
    """近期创新高：pct_from_high_60d 应约为 0，pct_from_low 应显著为正。"""
    closes = list(range(10, 90))  # 严格递增 80 行
    result = compute_quant_features(_mk_df(closes))
    p = result["price_position"]
    assert p["pct_from_high_60d"] is not None
    assert abs(p["pct_from_high_60d"]) < 0.01  # 就在 60 日高点
    assert p["pct_from_low_60d"] > 0.5  # 距 60 日低点已经飙 >50%


def test_limit_events_detects_9p7_percent_move():
    """构造一根 +10% 大阳，check limit_up_20d>=1。"""
    closes = [10.0] * 30
    closes[-1] = 11.0  # 最后一天 +10%
    df = _mk_df(closes)
    # 手动改 pct_chg 为 10.0（大于 9.7 阈值）
    df.loc[df.index[-1], "pct_chg"] = 10.0
    result = compute_quant_features(df)
    assert result["limit_events"]["limit_up_20d"] >= 1


def test_return_decomposition_direction():
    """构造 5 日全是"高开低走"：overnight 正、intraday 负。"""
    n = 30
    df = pd.DataFrame([
        {
            "trade_date": date(2024, 1, 1) + timedelta(days=i),
            "open": 11.0 + i * 0.1,       # 高开
            "high": 11.5 + i * 0.1,
            "low": 9.5 + i * 0.1,
            "close": 10.0 + i * 0.1,       # 低走
            "volume": 1_000_000,
            "amount": 10_000_000,
            "turnover": 1.5,
            "pct_chg": 0.0,
        }
        for i in range(n)
    ])
    result = compute_quant_features(df)
    rd = result["return_decomposition"]
    assert rd["overnight_return_5d"] is not None
    assert rd["intraday_return_5d"] is not None
    assert rd["overnight_return_5d"] > 0  # 隔夜跳空为正
    assert rd["intraday_return_5d"] < 0  # 日内为负
