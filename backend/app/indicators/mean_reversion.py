"""均值回归 / 左侧机会指标计算。

提供：偏离度、超卖统计、成交密集区、历史反弹概率。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def compute_mean_reversion(df: pd.DataFrame) -> dict:
    """计算均值回归相关指标。df 需含 close/volume/turnover/pct_chg，按 trade_date 升序。"""
    if df.empty or len(df) < 60:
        return {"insufficient_data": True}

    close = df["close"].astype(float)
    volume = df["volume"].astype(float)
    pct_chg = df["pct_chg"].astype(float).fillna(0)
    current_close = float(close.iloc[-1])

    # === 1. 偏离度 ===
    ma60 = float(close.rolling(60).mean().iloc[-1])
    ma120 = float(close.rolling(120).mean().iloc[-1]) if len(df) >= 120 else None
    deviation_ma60 = round((current_close - ma60) / ma60 * 100, 2)
    deviation_ma120 = round((current_close - ma120) / ma120 * 100, 2) if ma120 else None

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, np.nan)
    rsi14 = float((100 - 100 / (1 + rs)).iloc[-1])

    # 布林带位置百分位 (close 在 boll 带中的位置 0-100)
    ma20 = close.rolling(20).mean()
    std20 = close.rolling(20).std()
    boll_upper = ma20 + 2 * std20
    boll_lower = ma20 - 2 * std20
    boll_width = boll_upper - boll_lower
    boll_pct = ((close - boll_lower) / boll_width.replace(0, np.nan) * 100).iloc[-1]
    boll_pct = round(float(boll_pct), 1) if not np.isnan(boll_pct) else 50.0

    # 偏离度在近 120 日的分位（越低越超跌）
    deviation_series = (close - close.rolling(60).mean()) / close.rolling(60).mean() * 100
    tail_120 = deviation_series.tail(120).dropna()
    if len(tail_120) > 10:
        percentile = round(float((tail_120 < deviation_ma60).sum() / len(tail_120) * 100), 1)
    else:
        percentile = 50.0

    # === 2. 超卖统计 ===
    # 连跌天数
    consecutive_down = 0
    for p in reversed(pct_chg.values):
        if p < -0.1:
            consecutive_down += 1
        else:
            break

    # 近 10 日累计跌幅
    cum_10d = round(float(pct_chg.tail(10).sum()), 2)
    cum_20d = round(float(pct_chg.tail(20).sum()), 2)

    # 换手率萎缩（当日 vs 20日均值）
    turnover = df["turnover"].astype(float) if "turnover" in df.columns else None
    turnover_shrink = None
    if turnover is not None and len(turnover) >= 20:
        avg_turn_20 = float(turnover.tail(20).mean())
        cur_turn = float(turnover.iloc[-1])
        if avg_turn_20 > 0:
            turnover_shrink = round(cur_turn / avg_turn_20, 2)

    # === 3. 成交密集区（近 120 日按价格分段统计成交量） ===
    tail_120_df = df.tail(120)
    price_range = float(tail_120_df["high"].max() - tail_120_df["low"].min())
    support_zones = []
    if price_range > 0:
        n_bins = 10
        bin_size = price_range / n_bins
        low_val = float(tail_120_df["low"].min())
        bins = []
        for i in range(n_bins):
            bin_low = low_val + i * bin_size
            bin_high = bin_low + bin_size
            mask = (tail_120_df["close"].astype(float) >= bin_low) & (tail_120_df["close"].astype(float) < bin_high)
            vol = float(tail_120_df.loc[mask, "volume"].sum())
            bins.append({"low": round(bin_low, 2), "high": round(bin_high, 2), "volume": vol})

        # 按成交量排序取前 3 个在当前价下方的区间作为支撑
        bins_below = [b for b in bins if b["high"] <= current_close]
        bins_below.sort(key=lambda x: x["volume"], reverse=True)
        total_vol = sum(b["volume"] for b in bins)
        for b in bins_below[:3]:
            if b["volume"] > 0:
                strength = "strong" if b["volume"] / total_vol > 0.15 else "moderate" if b["volume"] / total_vol > 0.08 else "weak"
                support_zones.append({
                    "price_low": b["low"],
                    "price_high": b["high"],
                    "volume_pct": round(b["volume"] / total_vol * 100, 1),
                    "strength": strength,
                })

    # 前低点（近 60 日最低）
    recent_low_60 = round(float(close.tail(60).min()), 2)
    recent_low_20 = round(float(close.tail(20).min()), 2)

    # === 4. 历史反弹概率 ===
    # 当偏离度达到当前水平时，5/10/20 日后的涨跌统计
    bounce_stats = _compute_bounce_probability(deviation_series, deviation_ma60, pct_chg)

    return {
        "deviation": {
            "ma60_pct": deviation_ma60,
            "ma120_pct": deviation_ma120,
            "rsi14": round(rsi14, 1),
            "boll_pct": boll_pct,
            "percentile_120d": percentile,
        },
        "oversold": {
            "consecutive_down_days": consecutive_down,
            "cum_pct_10d": cum_10d,
            "cum_pct_20d": cum_20d,
            "turnover_vs_avg20": turnover_shrink,
        },
        "support_zones": support_zones,
        "reference_lows": {
            "low_20d": recent_low_20,
            "low_60d": recent_low_60,
        },
        "bounce_probability": bounce_stats,
    }


def _compute_bounce_probability(
    deviation_series: pd.Series,
    current_deviation: float,
    pct_chg: pd.Series,
) -> dict:
    """统计历史上偏离度到达当前水平时的反弹概率。"""
    if len(deviation_series) < 100:
        return {"insufficient_history": True}

    # 找历史上偏离度 <= 当前值的时刻（即历史上同样超跌的时刻）
    threshold = current_deviation + 1  # 允许 1% 容差
    similar_points = deviation_series[deviation_series <= threshold].index.tolist()

    if len(similar_points) < 5:
        return {"sample_size": len(similar_points), "insufficient_history": True}

    results = {}
    for horizon_days in [5, 10, 20]:
        gains = []
        for idx in similar_points:
            future_idx = idx + horizon_days
            if future_idx < len(pct_chg):
                future_return = float(pct_chg.iloc[idx + 1: future_idx + 1].sum())
                gains.append(future_return)
        if gains:
            positive = sum(1 for g in gains if g > 0)
            results[f"prob_{horizon_days}d"] = round(positive / len(gains) * 100, 1)
            results[f"avg_return_{horizon_days}d"] = round(np.mean(gains), 2)
            results[f"sample_{horizon_days}d"] = len(gains)

    return results
