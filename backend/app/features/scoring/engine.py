"""打分引擎入口：compute_indicator_cache（单指标预计算）+ score_stock（总分编排）。

拆分自原 stock_scorer.py 的组装层：将 golden/band/dividend 三因子合成综合分并暴露 components。
"""
from __future__ import annotations

import statistics

import pandas as pd

from app.indicators.adx import compute_adx
from app.indicators.macd import dif_slope as compute_dif_slope
from app.indicators.macd import is_golden, macd_series
from app.indicators.oscillators import compute_boll
from app.indicators.risk import compute_risk

from .band import _band_score, _dividend_score
from .golden import _cycle_stats, _golden_continuation, _peak_winrate
from .peak import _peak_features


def compute_indicator_cache(df: pd.DataFrame) -> dict:
    """扫描/判断公用的指标快照：score_stock 与 judge_trend 复用，避免同一 df 重复计算。

    返回 close/dif/dea/signals/dif_slope/golden/adx/boll/risk/acc_z/cycles。
    独立调用（如详情页）可不传 cache，由各函数自行计算。
    """
    close = df["close"].astype(float)
    dif, dea, signals = macd_series(close)
    cycles = _cycle_stats(close, signals)
    peak = _peak_features(close, dif, dea, df["volume"])
    return {
        "close": close,
        "dif": dif,
        "dea": dea,
        "signals": signals,
        "dif_slope": compute_dif_slope(dif),
        "golden": is_golden(dif, dea),
        "adx": compute_adx(df),
        "boll": compute_boll(df),
        "risk": compute_risk(df),
        "acc_z": peak["acc_z"],
        "slope_up": peak["slope_up"],
        "peak_signal": peak["peak_signal"],
        "peak_conf": peak["peak_conf"],
        "vr20": peak["vr20"],
        "cycles": cycles,
        "peak_winrate": _peak_winrate(cycles[0]),
    }


def score_stock(df: pd.DataFrame, dividend_yield: float | None = None,
                is_fund: bool = False, cache: dict | None = None,
                timeframe: str = "daily") -> dict | None:
    """对单只标的打分（金叉延续 ×0.70 + 波段 ×0.20 + 股息 ×0.10）。

    df 需含 trade_date/open/high/low/close/volume/amount（升序）。投后字典 PO 部 DM。
    cache：compute_indicator_cache 预计算指标（扫描复用），None 时自行计算。
    timeframe：打分基于的 K 线周期（daily/weekly），跨入 `_band_score` 做波动率尺度折换。
    """
    if df is None or df.empty or len(df) < 60:  # _MIN_ROWS
        return None
    if "trade_date" in df.columns:
        df = df.sort_values("trade_date").reset_index(drop=True)

    # 各维度分数
    golden = _golden_continuation(df, cache=cache)
    band = _band_score(df, timeframe=timeframe)
    dividend = _dividend_score(dividend_yield, is_fund)

    # 权重：金叉延续 70% + 波段 20% + 股息 10%
    total = (0.70 * golden["score"]
             + 0.20 * band["score"]
             + 0.10 * dividend["score"])

    latest = df.iloc[-1]
    close = float(latest["close"])
    pct_chg = float(latest["pct_chg"]) if pd.notna(latest.get("pct_chg")) else None
    turnover = float(latest["turnover"]) if pd.notna(latest.get("turnover")) else None
    # compute_indicator_cache 已算过 risk，直接用，避免重复计算（扫描 4000 只时省 2 倍）
    hist_vol = (cache["risk"]["hist_vol_20d"] if cache else compute_risk(df).get("hist_vol_20d"))

    return {
        "total_score": round(total, 1),
        "signal_score": round(golden["score"], 1),  # 金叉延续性分（主成分）
        "band_score": round(band["score"], 1),
        "dividend_score": round(dividend["score"], 1),
        "close": close,
        "pct_chg": pct_chg,
        "turnover": turnover,
        "hist_vol": hist_vol,
        "adx": golden["adx"],
        "dividend_yield": dividend_yield,
        "components": {
            "signal": golden,
            "band": band,
            "dividend": dividend,
        },
    }
