"""趋势/可入手判断（金叉驱动）：MACD 金叉死叉为主导，BOLL + 距高点衡量潜在空间。

决策口径：
- 金叉态（DIF > DEA）= 上升候选：
  - 贴上轨（%B 高）→ 短期过热，等回踩
  - 距 60 日高点回撤极深（<-40%）且历史金叉延续差 → 深跌中刚金叉，不可靠
  - 历史金叉延续可靠（signal 分高）→ 可入手
  - 否则只要未过热、有空间 → 可入手
- 死叉态：历史金叉可靠（signal 高分）→ 等下次金叉（观望）；否则下跌趋势回避

MA 结构 / ADX / RSI 降为辅助参考（indicators），不再一票否决——MA 滞后，
反映不了 MACD 金叉的即时信号（实测高分股金叉态却被 MA 空头误判 downtrend）。
"""
from __future__ import annotations

import pandas as pd

from app.indicators.adx import compute_adx
from app.indicators.ma import compute_ma
from app.indicators.macd import dif_slope as compute_dif_slope
from app.indicators.macd import is_golden, macd_series
from app.indicators.oscillators import compute_boll
from app.indicators.risk import compute_risk

_MIN_ROWS = 60  # MACD EMA26 预热需要 ~60 根

# 金叉延续分阈值：>= 此值视为历史金叉可靠
_SIGNAL_RELIABLE = 65

_REASONS = {
    "pullback_entry": "金叉态·上方空间足，可入手",
    "overheat": "金叉态但贴上轨（短期过热），等回踩",
    "downtrend": "死叉态·历史金叉延续差，回避",
    "range": "观望（等金叉或信号不明）",
    "insufficient": "历史数据不足（需 ≥60 根日线）",
}


def _decide_stage(golden: bool, pct_b: float | None, dist_high: float,
                  signal_score: float | None) -> str:
    """金叉驱动的阶段决策（纯逻辑，无 I/O，可直接单测）。

    - 金叉态 = 上升候选：贴上轨→过热；深跌且历史差→下跌；历史可靠→可入手；
      未过热有空间→可入手；否则贴下轨（%B<0.2 弱势）→震荡
    - 死叉态：历史可靠→观望等下次金叉；否则→下跌回避
    """
    if golden:
        if pct_b is not None and pct_b > 0.85:
            return "overheat"  # 贴上轨，短期涨过头
        if dist_high < -0.4 and (signal_score is None or signal_score < _SIGNAL_RELIABLE):
            return "downtrend"  # 深跌中刚金叉且历史不可靠
        if signal_score is not None and signal_score >= _SIGNAL_RELIABLE:
            return "pullback_entry"  # 金叉 + 历史可靠 → 可入手
        if pct_b is None or pct_b >= 0.2:
            return "pullback_entry"  # 金叉、未过热、有上方空间
        return "range"  # 金叉但贴下轨（弱势）
    if signal_score is not None and signal_score >= _SIGNAL_RELIABLE:
        return "range"  # 历史金叉可靠，等下次金叉
    return "downtrend"  # 死叉 + 历史差 → 回避


def judge_trend(df: pd.DataFrame, signal_score: float | None = None) -> dict:
    """对单只标的做金叉驱动的趋势/可入手判断。

    df 需含 trade_date/open/high/low/close/volume/amount/turnover/pct_chg（升序）。
    signal_score 为金叉延续性分（0-100，历史可靠性），由打分引擎提供，可 None。
    返回 {trend_stage, can_entry, entry_reason, key_prices, indicators}。
    """
    if df is None or df.empty or len(df) < _MIN_ROWS:
        return {
            "trend_stage": "insufficient",
            "can_entry": False,
            "entry_reason": "历史数据不足（需 ≥60 根日线）",
            "key_prices": {},
            "indicators": {},
        }
    if "trade_date" in df.columns:
        df = df.sort_values("trade_date").reset_index(drop=True)

    close_s = df["close"].astype(float)
    close = float(close_s.iloc[-1])

    # MACD 金叉状态 + DIF 斜率（indicators/macd 统一实现，与打分引擎共用）
    dif, dea, _signals = macd_series(close_s)
    golden = is_golden(dif, dea)
    dif_slope = compute_dif_slope(dif)

    # 潜在空间：BOLL %B/带宽 + 距 60 日高点回撤
    boll = compute_boll(df)
    pct_b = boll["pct_b"]
    bandwidth = boll["bandwidth"]
    high_60 = float(df["high"].tail(60).max()) if len(df) >= 60 else float(df["high"].max())
    dist_high = close / high_60 - 1 if high_60 else 0.0

    # 决策：金叉死叉为主导（纯逻辑，见 _decide_stage）
    stage = _decide_stage(golden, pct_b, dist_high, signal_score)

    # 辅助参考（不参与决策）
    adx_info = compute_adx(df)
    arrangement = compute_ma(df).get("arrangement")
    stop_loss = compute_risk(df).get("stop_loss_hint")

    ma20 = boll["middle"]
    ma60 = float(close_s.rolling(60).mean().iloc[-1]) if len(df) >= 60 else None
    ma120 = float(close_s.rolling(120).mean().iloc[-1]) if len(df) >= 120 else None

    return {
        "trend_stage": stage,
        "can_entry": stage == "pullback_entry",
        "entry_reason": _REASONS.get(stage, ""),
        "key_prices": {
            "close": round(close, 3),
            "ma20": round(ma20, 3) if ma20 is not None else None,
            "ma60": round(ma60, 3) if ma60 is not None else None,
            "ma120": round(ma120, 3) if ma120 is not None else None,
            "resistance_60d": round(high_60, 3),
            "stop_loss": stop_loss,
        },
        "indicators": {
            "adx": adx_info["adx"],
            "plus_di": adx_info["plus_di"],
            "minus_di": adx_info["minus_di"],
            "arrangement": arrangement,
            # 金叉 + 空间因子
            "golden": golden,
            "dif": round(float(dif.iloc[-1]), 4) if pd.notna(dif.iloc[-1]) else None,
            "dea": round(float(dea.iloc[-1]), 4) if pd.notna(dea.iloc[-1]) else None,
            "dif_slope": dif_slope,
            "pct_b": round(pct_b, 3) if pct_b is not None else None,
            "bandwidth": round(bandwidth, 4) if bandwidth is not None else None,
            "dist_high_60_pct": round(dist_high * 100, 2),
        },
    }
