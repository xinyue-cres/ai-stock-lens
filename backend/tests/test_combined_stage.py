"""综合档位矩阵与对称加成的回归测试（docs/state-machine-redesign.md v0.3）。"""
from __future__ import annotations

import pytest

from app.features.combined_judge import (
    _SCORE_BONUS,
    combined_entry_reason,
    combined_meta,
    combined_score,
    combined_stage,
)


# ---------------------------------------------------------------------------
# 矩阵关键组合
# ---------------------------------------------------------------------------

def test_buy_side_resonance():
    assert combined_stage("pullback_entry", "pullback_entry") == "strong_buy"
    assert combined_stage("strong_uptrend", "strong_uptrend") == "strong_buy"


def test_watch_sell_dual_weak():
    # 周弱 / 假金叉 + 日走弱 → 卖侧观察，而非直接 avoid
    assert combined_stage("weak_golden", "pullback_entry") == "watch_sell"
    assert combined_stage("left_entry", "weak_golden") == "watch_sell"


def test_sell_side_downtrend_fine_grained():
    # 周下跌不再是整行 avoid：双周共振死叉才清仓，其余按力度分级
    assert combined_stage("downtrend", "downtrend") == "strong_sell"
    assert combined_stage("downtrend", "overheat") == "sell"
    assert combined_stage("downtrend", "range") == "sell"
    assert combined_stage("downtrend", "strong_uptrend") == "deep_rally_exit"
    assert combined_stage("downtrend", "pullback_entry") == "watch_sell"


def test_overheat_side_fine_grained():
    assert combined_stage("overheat", "overheat") == "strong_sell"
    assert combined_stage("overheat", "downtrend") == "strong_sell"
    assert combined_stage("overheat", "strong_uptrend") == "sell"
    assert combined_stage("overheat", "range") == "watch_sell"


def test_avoid_only_no_eval():
    # avoid 仅保留"系统不评估"兜底：数据不足 / 双周假弱无方向
    assert combined_stage("weak_golden", "weak_golden") == "avoid"
    assert combined_stage("weak_golden", "range") == "avoid"
    assert combined_stage("downtrend", "insufficient") == "avoid"
    assert combined_stage("overheat", "insufficient") == "avoid"
    # 其余卖侧组合不应落到 avoid
    assert combined_stage("downtrend", "downtrend") != "avoid"


def test_hold_center():
    assert combined_stage("range", "range") == "hold"
    assert combined_stage("left_entry", "left_entry") == "hold"
    assert combined_stage("insufficient", "pullback_entry") == "hold"


def test_unknown_falls_back_to_hold():
    # 未列出的组合 → hold（保守，可交易但不行动）
    assert combined_stage("range", "strange_stage") == "hold"


# ---------------------------------------------------------------------------
# 镜像对称加成
# ---------------------------------------------------------------------------

def test_bonus_mirror_symmetry():
    pairs = [
        ("strong_buy", "strong_sell", 8),
        ("buy", "sell", 4),
        ("watch_buy", "watch_sell", 1),
        ("light_buy", "light_sell", 2),
        ("deep_pullback_entry", "deep_rally_exit", 2),
    ]
    for buy_side, sell_side, mag in pairs:
        assert _SCORE_BONUS[buy_side] == mag, f"{buy_side} 加成应为 +{mag}"
        assert _SCORE_BONUS[sell_side] == -mag, f"{sell_side} 加成应为 -{mag}"
    assert _SCORE_BONUS["hold"] == 0
    assert _SCORE_BONUS["avoid"] == -99


def test_score_clip_and_bonus():
    # 卖侧负加成保留 base 梯度，不一律压 0
    assert combined_score(60, 60, "sell") == 0.6 * 60 + 0.4 * 60 - 4
    # 低分卖侧可能触底，但高分卖侧保留区分度
    s_high = combined_score(80, 80, "strong_sell")
    assert s_high > 0 and s_high == 0.6 * 80 + 0.4 * 80 - 8
    # avoid 强制沉底
    assert combined_score(80, 80, "avoid") == 0.0
    # 极端高分 clip 到 100
    assert combined_score(99, 99, "strong_buy") <= 100.0


# ---------------------------------------------------------------------------
# 元数据完整性
# ---------------------------------------------------------------------------

def test_all_stages_have_meta():
    stages = ["strong_buy", "buy", "watch_buy", "deep_pullback_entry", "light_buy",
              "hold", "watch_sell", "light_sell", "deep_rally_exit", "sell",
              "strong_sell", "avoid"]
    for s in stages:
        meta = combined_meta(s)
        assert meta["label"], f"{s} 缺 label"
        assert meta["action"], f"{s} 缺 action"
        assert meta["reason"], f"{s} 缺 reason"


def test_entry_reason_covers_sell_side():
    weekly = {"trend_stage": "downtrend", "peak_signal": None}
    daily = {"trend_stage": "downtrend", "peak_signal": "下跌过峰", "peak_conf": 45}
    r = combined_entry_reason("strong_sell", weekly, daily)
    assert "周线 downtrend" in r or "日线 downtrend" in r
    assert "下跌过峰" in r
