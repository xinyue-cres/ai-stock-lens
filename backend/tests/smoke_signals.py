"""信号引擎烟雾测试。"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.indicators.signals import scan_signals


def test_bullish_setup():
    indicators = {
        "ma": {
            "ma5": 12.0, "ma10": 11.0, "ma20": 10.5, "ma60": 10.0,
            "arrangement": "bullish",
            "ma5_ma10_cross": "golden",
            "ma5_ma20_cross": None,
        },
        "oscillators": {
            "macd": {"cross": "golden"},
            "kdj": {"signal": "neutral"},
            "boll": {"position": "above_upper"},
        },
        "volume": {"volume_pattern": "big_volume_up", "vol_ratio": 3.5},
        "patterns": ["突破 60 日新高"],
        "rs": {"pct_20d": 25},
    }
    signals = scan_signals(indicators)
    keys = [s["key"] for s in signals]
    assert "ma_bullish_arrangement" in keys
    assert "ma_golden_5_10" in keys
    assert "macd_golden" in keys
    assert "boll_above_upper" in keys
    assert "vol_big_up" in keys
    assert "pat_break_60d_high" in keys
    assert "rs_strong_20d" in keys
    # 按权重降序
    assert signals[0]["weight"] >= signals[-1]["weight"]
    print(f"✓ bullish 场景 {len(signals)} 条信号，top: {signals[0]['label']}")


def test_bearish_setup():
    indicators = {
        "ma": {
            "ma5": 8.0, "ma10": 9.0, "ma20": 10.0, "ma60": 11.0,
            "arrangement": "bearish",
            "ma5_ma10_cross": "death",
            "ma5_ma20_cross": "death",
        },
        "oscillators": {
            "macd": {"cross": "death"},
            "kdj": {"signal": "overbought"},
            "boll": {"position": "below_lower"},
        },
        "volume": {"volume_pattern": "big_volume_down", "vol_ratio": 4.0},
        "patterns": ["跌破 20 日新低", "下穿 5 日均线"],
        "rs": {"pct_20d": -20},
    }
    signals = scan_signals(indicators)
    directions = [s["direction"] for s in signals]
    assert directions.count("bearish") >= 5
    print(f"✓ bearish 场景 {len(signals)} 条信号")


def test_empty():
    assert scan_signals({}) == []
    assert scan_signals({"empty": True}) == []
    print("✓ 空输入返回 []")


if __name__ == "__main__":
    test_bullish_setup()
    test_bearish_setup()
    test_empty()
