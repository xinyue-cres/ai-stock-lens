"""趋势判断单元测试：金叉驱动决策 + 数据不足。

合成 K 线的 MACD 金叉态窗口很窄（刚金叉、价格贴中轨），单调序列难以稳定命中
"金叉 + %B 适中 = 可入手"；因此这里覆盖可可靠构造的分支：死叉态（signal 高→观望
/低→回避）、金叉态贴上轨（→过热）、数据不足。
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from app.features.trend_judge import _decide_stage, judge_trend


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


def test_left_entry_deadcross_high_signal():
    """死叉态下跌过峰（柱缩）且历史金叉延续可靠 → 左侧机会。"""
    closes = list(np.linspace(10, 20, 80)) + list(np.linspace(20, 14, 70))
    r = judge_trend(_mk_df(closes), signal_score=85)
    assert r["trend_stage"] == "left_entry"


def test_overheat_golden_touches_upper():
    """金叉态但贴上轨（%B 高）→ 短期过热，等回踩。"""
    closes = list(np.linspace(20, 10, 80)) + list(np.linspace(10, 14, 70))
    r = judge_trend(_mk_df(closes), signal_score=85)
    assert r["trend_stage"] == "overheat"
    assert r["indicators"]["pct_b"] is not None
    assert r["indicators"]["pct_b"] > 0.85


# ---------------------------------------------------------------------------
# _decide_stage 纯逻辑单测：不依赖合成 K 线，直接覆盖决策树全部分支
# ---------------------------------------------------------------------------

def test_decide_stage_overheat():
    assert _decide_stage(golden=True, pct_b=0.9, dist_high=-0.1, signal_score=85) == "overheat"


def test_decide_stage_golden_deep_drawdown_unreliable():
    # 深跌中刚金叉 + 历史金叉延续不可靠 → 下跌
    assert _decide_stage(golden=True, pct_b=0.5, dist_high=-0.5, signal_score=50) == "downtrend"


def test_decide_stage_golden_reliable():
    # 历史金叉延续可靠 → 可入手（优先于"有空间"）
    assert _decide_stage(golden=True, pct_b=0.5, dist_high=-0.2, signal_score=70) == "pullback_entry"


def test_decide_stage_golden_space():
    # 未过热、有上方空间 → 可入手；%B None（无带）也视为有空间
    assert _decide_stage(golden=True, pct_b=0.5, dist_high=-0.2, signal_score=50) == "pullback_entry"
    assert _decide_stage(golden=True, pct_b=None, dist_high=-0.1, signal_score=50) == "pullback_entry"


def test_decide_stage_golden_weak_lower_band():
    # 金叉但贴下轨（%B<0.2 弱势）→ 震荡观望
    assert _decide_stage(golden=True, pct_b=0.1, dist_high=-0.1, signal_score=50) == "range"


def test_decide_stage_deadcross():
    # 死叉态：历史可靠→观望；否则→下跌
    assert _decide_stage(golden=False, pct_b=0.5, dist_high=-0.1, signal_score=85) == "range"
    assert _decide_stage(golden=False, pct_b=0.5, dist_high=-0.1, signal_score=50) == "downtrend"
    assert _decide_stage(golden=False, pct_b=0.5, dist_high=-0.1, signal_score=None) == "downtrend"


# 新增分支：左侧机会 / 弱势金叉 / 上升趋势
def test_decide_stage_left_entry():
    # 死叉态 + 下跌过峰（bar_shrinking=False 绿柱回升）+ 历史可靠 → 左侧机会
    assert _decide_stage(golden=False, pct_b=0.5, dist_high=-0.3, signal_score=85,
                         bar_shrinking=False) == "left_entry"


def test_decide_stage_left_entry_rejected_if_unreliable():
    # 死叉 + 过峰但历史差 → 仍下跌
    assert _decide_stage(golden=False, pct_b=0.5, dist_high=-0.3, signal_score=50,
                         bar_shrinking=False) == "downtrend"


def test_decide_stage_weak_golden():
    # 金叉态 + 柱体缩小（上涨过峰）→ 弱势金叉，别追
    assert _decide_stage(golden=True, pct_b=0.5, dist_high=-0.2, signal_score=85,
                         bar_shrinking=True) == "weak_golden"


def test_decide_stage_strong_uptrend():
    # 金叉态 + ADX 强 + 已涨一段 + 柱体未缩小 → 可持有不追高
    assert _decide_stage(golden=True, pct_b=0.5, dist_high=-0.1, signal_score=85,
                         bar_shrinking=False, adx=30.0, signal_gain_pct=10.0) == "strong_uptrend"


def test_decide_stage_strong_uptrend_needs_gain():
    # ADX 强但还没涨到 8% → 不判强趋势，走普通可入手
    assert _decide_stage(golden=True, pct_b=0.5, dist_high=-0.1, signal_score=85,
                         bar_shrinking=False, adx=30.0, signal_gain_pct=3.0) == "pullback_entry"


def test_decide_stage_strong_uptrend_needs_adx():
    # ADX 弱 → 不判强趋势，走普通可入手
    assert _decide_stage(golden=True, pct_b=0.5, dist_high=-0.1, signal_score=85,
                         bar_shrinking=False, adx=15.0, signal_gain_pct=10.0) == "pullback_entry"


def test_decide_stage_overheat_strong_trend():
    # 强趋势 + 贴上轨 → 不算过热（强趋势贴轨是顺势），走 strong_uptrend
    assert _decide_stage(golden=True, pct_b=0.9, dist_high=-0.1, signal_score=85,
                         bar_shrinking=False, adx=30.0, signal_gain_pct=10.0) == "strong_uptrend"


def test_decide_stage_overheat_weak_trend():
    # 非强趋势 + 贴上轨 → 过热
    assert _decide_stage(golden=True, pct_b=0.9, dist_high=-0.1, signal_score=85,
                         bar_shrinking=False, adx=15.0, signal_gain_pct=10.0) == "overheat"
