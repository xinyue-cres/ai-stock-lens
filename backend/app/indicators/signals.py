"""信号规则引擎。

输入：某只股票的 indicators dict（compute_all 输出）
输出：list[Signal]，每条信号带类别、方向、置信度、说明。

信号仅描述"当日发生了什么"，不给出买卖建议——那是 AI 报告的职责。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass
class Signal:
    key: str            # 唯一 key，如 "ma_golden_cross_5_20"
    category: str       # ma | oscillator | volume | pattern | strength
    direction: str      # bullish | bearish | neutral
    label: str          # 中文标签，前端直接展示
    detail: str = ""    # 详细说明
    weight: float = 1.0 # 权重（用于排序，越大越显著）


def scan_signals(indicators: dict) -> list[dict]:
    """按类别扫描，返回可序列化的 dict 列表。"""
    if not indicators or indicators.get("empty"):
        return []

    signals: list[Signal] = []

    ma = indicators.get("ma") or {}
    osc = indicators.get("oscillators") or {}
    vol = indicators.get("volume") or {}
    patterns: list[str] = indicators.get("patterns") or []
    rs = indicators.get("rs") or {}

    signals += _ma_signals(ma)
    signals += _macd_signals(osc.get("macd") or {})
    signals += _kdj_signals(osc.get("kdj") or {})
    signals += _boll_signals(osc.get("boll") or {})
    signals += _volume_signals(vol)
    signals += _pattern_signals(patterns)
    signals += _rs_signals(rs)

    return [asdict(s) for s in sorted(signals, key=lambda x: -x.weight)]


def _ma_signals(ma: dict) -> list[Signal]:
    out: list[Signal] = []
    arrangement = ma.get("arrangement")
    if arrangement == "bullish":
        out.append(Signal("ma_bullish_arrangement", "ma", "bullish", "均线多头排列", weight=2.5))
    elif arrangement == "bearish":
        out.append(Signal("ma_bearish_arrangement", "ma", "bearish", "均线空头排列", weight=2.5))
    elif arrangement == "tangled":
        out.append(Signal("ma_tangled", "ma", "neutral", "均线纠缠", weight=1.0))

    cross_5_10 = ma.get("ma5_ma10_cross")
    if cross_5_10 == "golden":
        out.append(Signal("ma_golden_5_10", "ma", "bullish", "MA5 上穿 MA10", weight=1.8))
    elif cross_5_10 == "death":
        out.append(Signal("ma_death_5_10", "ma", "bearish", "MA5 下穿 MA10", weight=1.8))

    cross_5_20 = ma.get("ma5_ma20_cross")
    if cross_5_20 == "golden":
        out.append(Signal("ma_golden_5_20", "ma", "bullish", "MA5 上穿 MA20", weight=2.2))
    elif cross_5_20 == "death":
        out.append(Signal("ma_death_5_20", "ma", "bearish", "MA5 下穿 MA20", weight=2.2))

    return out


def _macd_signals(macd: dict) -> list[Signal]:
    cross = macd.get("cross")
    if cross == "golden":
        return [Signal("macd_golden", "oscillator", "bullish", "MACD 金叉", weight=2.4)]
    if cross == "death":
        return [Signal("macd_death", "oscillator", "bearish", "MACD 死叉", weight=2.4)]
    return []


def _kdj_signals(kdj: dict) -> list[Signal]:
    sig = kdj.get("signal")
    if sig == "overbought":
        return [Signal("kdj_overbought", "oscillator", "bearish", "KDJ 超买", weight=1.5)]
    if sig == "oversold":
        return [Signal("kdj_oversold", "oscillator", "bullish", "KDJ 超卖", weight=1.5)]
    return []


def _boll_signals(boll: dict) -> list[Signal]:
    pos = boll.get("position")
    if pos == "above_upper":
        return [Signal("boll_above_upper", "oscillator", "bullish", "突破 BOLL 上轨", weight=2.0)]
    if pos == "below_lower":
        return [Signal("boll_below_lower", "oscillator", "bearish", "跌破 BOLL 下轨", weight=2.0)]
    return []


def _volume_signals(vol: dict) -> list[Signal]:
    p = vol.get("volume_pattern")
    vr = vol.get("vol_ratio")
    detail = f"量比 {vr}" if vr else ""
    if p == "big_volume_up":
        return [Signal("vol_big_up", "volume", "bullish", "放量上涨", detail, weight=2.6)]
    if p == "big_volume_down":
        return [Signal("vol_big_down", "volume", "bearish", "放量下跌", detail, weight=2.6)]
    if p == "big_volume_flat":
        return [Signal("vol_big_flat", "volume", "neutral", "放量滞涨", detail, weight=1.6)]
    if p == "shrink_volume":
        return [Signal("vol_shrink", "volume", "neutral", "缩量整理", detail, weight=0.8)]
    return []


def _pattern_signals(patterns: list[str]) -> list[Signal]:
    out: list[Signal] = []
    mapping = {
        "突破 20 日新高": Signal("pat_break_20d_high", "pattern", "bullish", "突破 20 日新高", weight=2.7),
        "突破 60 日新高": Signal("pat_break_60d_high", "pattern", "bullish", "突破 60 日新高", weight=3.0),
        "跌破 20 日新低": Signal("pat_break_20d_low", "pattern", "bearish", "跌破 20 日新低", weight=2.7),
        "跌破 60 日新低": Signal("pat_break_60d_low", "pattern", "bearish", "跌破 60 日新低", weight=3.0),
        "上穿 5 日均线": Signal("pat_up_ma5", "pattern", "bullish", "上穿 5 日均线", weight=1.4),
        "下穿 5 日均线": Signal("pat_down_ma5", "pattern", "bearish", "下穿 5 日均线", weight=1.4),
        "上影线较长（阻力显现）": Signal("pat_long_upper_shadow", "pattern", "bearish", "长上影阻力显现", weight=1.2),
        "下影线较长（支撑显现）": Signal("pat_long_lower_shadow", "pattern", "bullish", "长下影支撑显现", weight=1.2),
    }
    for p in patterns:
        if p in mapping:
            out.append(mapping[p])
    return out


def _rs_signals(rs: dict) -> list[Signal]:
    out: list[Signal] = []
    pct_20d = rs.get("pct_20d")
    if isinstance(pct_20d, int | float):
        if pct_20d >= 20:
            out.append(Signal("rs_strong_20d", "strength", "bullish", f"20 日强势 +{pct_20d:.1f}%", weight=1.6))
        elif pct_20d <= -15:
            out.append(Signal("rs_weak_20d", "strength", "bearish", f"20 日弱势 {pct_20d:.1f}%", weight=1.6))
    return out
