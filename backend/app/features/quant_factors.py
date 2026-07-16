"""量化视角的因子提取器。

面向 AI Agent 输入设计：跟人类交易者关注的 MACD/KDJ 完全不同，
这里是量化机构真实会看的因子（动量、波动率、流动性、量能异常等）。
将来加更多 agent 视角，可在 app/features/ 下加新模块（不污染 indicators/）。
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def _safe(v: Any) -> float | None:
    """把 NaN/Inf/None 归一化为 None（用于 JSON 序列化）。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(f):
        return None
    return round(f, 6)


def _cum_return(closes: pd.Series, n: int) -> float | None:
    if len(closes) <= n:
        return None
    start, end = float(closes.iloc[-n - 1]), float(closes.iloc[-1])
    if start <= 0:
        return None
    return (end - start) / start


def _sigma(closes: pd.Series, n: int) -> float | None:
    if len(closes) < n + 1:
        return None
    rets = closes.pct_change().dropna().tail(n)
    if len(rets) < n // 2:
        return None
    return float(rets.std(ddof=0))


def _atr_ratio(df: pd.DataFrame, n: int = 14) -> float | None:
    """ATR / close，占比化的波动率。"""
    if len(df) < n + 1:
        return None
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    atr = tr.tail(n).mean()
    latest_close = float(close.iloc[-1])
    if latest_close <= 0:
        return None
    return float(atr / latest_close)


def _amihud(df: pd.DataFrame, n: int = 20) -> float | None:
    """Amihud illiquidity: mean(|return| / (volume × close))。放大后单位为 1e-9。"""
    if len(df) < n + 1:
        return None
    tail = df.tail(n + 1).copy()
    tail["ret"] = tail["close"].pct_change().abs()
    tail["dollar_vol"] = tail["volume"].astype(float) * tail["close"].astype(float)
    tail = tail.iloc[1:]  # 丢第一行（pct_change=NaN）
    tail = tail[tail["dollar_vol"] > 0]
    if tail.empty:
        return None
    illiq = (tail["ret"] / tail["dollar_vol"]).mean()
    return float(illiq * 1e9)  # 放大到可读量级


def _zscore(series: pd.Series, window: int) -> float | None:
    """当前值相对 window 期均值的 z-score。"""
    if len(series) < window + 1:
        return None
    ref = series.iloc[-window - 1:-1]
    mean, std = float(ref.mean()), float(ref.std(ddof=0))
    if std == 0:
        return None
    return (float(series.iloc[-1]) - mean) / std


def compute_quant_features(df: pd.DataFrame) -> dict:
    """输入按 trade_date 升序的日线 df，输出量化因子快照。

    df 必须含列：trade_date, open, high, low, close, volume, amount, turnover, pct_chg。
    数据不足时相关字段返回 None，AI 会知道缺哪些。
    """
    if df is None or df.empty:
        return {"empty": True}

    df = df.sort_values("trade_date").reset_index(drop=True)
    close = df["close"].astype(float)
    open_ = df["open"].astype(float)
    volume = df["volume"].astype(float)
    turnover = df["turnover"].astype(float) if "turnover" in df.columns else pd.Series([], dtype=float)
    pct_chg = df["pct_chg"].astype(float) if "pct_chg" in df.columns else pd.Series([], dtype=float)

    # ----- momentum -----
    momentum = {
        "return_20d": _safe(_cum_return(close, 20)),
        "return_60d": _safe(_cum_return(close, 60)),
        "return_120d": _safe(_cum_return(close, 120)),
    }

    # ----- volatility -----
    volatility = {
        "sigma_20d": _safe(_sigma(close, 20)),
        "sigma_60d": _safe(_sigma(close, 60)),
        "atr_ratio_14d": _safe(_atr_ratio(df, 14)),
    }

    # ----- liquidity -----
    liquidity: dict = {
        "amihud_20d": _safe(_amihud(df, 20)),
        "turnover_mean_20d": None,
        "turnover_z_5d_vs_60d": None,
        "turnover_percentile_120d": None,
    }
    if not turnover.dropna().empty and len(turnover.dropna()) >= 20:
        # 只取有效换手率
        valid = turnover.dropna()
        liquidity["turnover_mean_20d"] = _safe(valid.tail(20).mean())
        if len(valid) >= 61:
            # 近 5 日均值 vs 前 60 日均值的 z（用前 60 日 std）
            recent5 = valid.tail(5).mean()
            ref60 = valid.iloc[-65:-5]
            ref_mean, ref_std = float(ref60.mean()), float(ref60.std(ddof=0))
            if ref_std > 0:
                liquidity["turnover_z_5d_vs_60d"] = _safe((float(recent5) - ref_mean) / ref_std)
        if len(valid) >= 120:
            latest_turnover = float(valid.iloc[-1])
            window120 = valid.tail(120)
            percentile = float((window120 < latest_turnover).sum()) / 120.0
            liquidity["turnover_percentile_120d"] = _safe(percentile)

    # ----- volume anomaly -----
    vol_anomaly: dict = {
        "vol_ratio_5d_vs_60d": None,
        "vol_z_60d": _safe(_zscore(volume, 60)),
        "big_volume_days_20d": None,
    }
    if len(volume) >= 65:
        avg_5 = float(volume.tail(5).mean())
        avg_60 = float(volume.iloc[-65:-5].mean())
        if avg_60 > 0:
            vol_anomaly["vol_ratio_5d_vs_60d"] = _safe(avg_5 / avg_60)
    if len(volume) >= 25:
        ref60 = volume.iloc[-min(len(volume), 80):-20]
        if not ref60.empty:
            mean60 = float(ref60.mean())
            if mean60 > 0:
                big = (volume.tail(20) / mean60 >= 2.0).sum()
                vol_anomaly["big_volume_days_20d"] = int(big)

    # ----- price position -----
    price_pos: dict = {
        "pct_from_high_60d": None,
        "pct_from_low_60d": None,
        "close_over_ma60": None,
        "distance_to_ma20_pct": None,
        "boll_position": None,
    }
    if len(close) >= 60:
        latest = float(close.iloc[-1])
        window = close.tail(60)
        high60, low60 = float(window.max()), float(window.min())
        if high60 > 0:
            price_pos["pct_from_high_60d"] = _safe((latest - high60) / high60)
        if low60 > 0:
            price_pos["pct_from_low_60d"] = _safe((latest - low60) / low60)
        ma60 = float(window.mean())
        if ma60 > 0:
            price_pos["close_over_ma60"] = _safe(latest / ma60 - 1)
    if len(close) >= 20:
        latest = float(close.iloc[-1])
        ma20 = float(close.tail(20).mean())
        if ma20 > 0:
            price_pos["distance_to_ma20_pct"] = _safe((latest - ma20) / ma20)
        # Bollinger band position: (close - lower) / (upper - lower)
        std20 = float(close.tail(20).std(ddof=0))
        boll_upper = ma20 + 2 * std20
        boll_lower = ma20 - 2 * std20
        boll_width = boll_upper - boll_lower
        if boll_width > 0:
            price_pos["boll_position"] = _safe((latest - boll_lower) / boll_width)

    # ----- price-volume confirmation -----
    pv_confirm: dict = {"up_volume_ratio": None}
    if len(df) >= 21:
        tail20 = df.tail(20).copy()
        tail20["ret"] = tail20["close"].astype(float).pct_change()
        tail20 = tail20.iloc[1:]  # drop first NaN
        up_days = tail20[tail20["ret"] > 0]
        down_days = tail20[tail20["ret"] < 0]
        if not down_days.empty and not up_days.empty:
            avg_up_vol = float(up_days["volume"].astype(float).mean())
            avg_down_vol = float(down_days["volume"].astype(float).mean())
            if avg_down_vol > 0:
                pv_confirm["up_volume_ratio"] = _safe(avg_up_vol / avg_down_vol)

    # ----- return decomposition -----
    return_decomp: dict = {"overnight_return_5d": None, "intraday_return_5d": None}
    if len(df) >= 6:
        tail = df.tail(6).copy()
        prev_close = tail["close"].shift(1)
        overnight = (tail["open"] / prev_close - 1).iloc[1:]  # 6 行 shift 后取后 5 行
        intraday = (tail["close"] / tail["open"] - 1).iloc[1:]
        # 累计（复利式相加简单版）
        return_decomp["overnight_return_5d"] = _safe(overnight.sum())
        return_decomp["intraday_return_5d"] = _safe(intraday.sum())

    # ----- limit events -----
    limit_events: dict = {
        "limit_up_20d": 0, "limit_down_20d": 0, "gap_up_20d": 0,
    }
    if not pct_chg.dropna().empty:
        recent20 = pct_chg.tail(20)
        limit_events["limit_up_20d"] = int((recent20 >= 9.7).sum())
        limit_events["limit_down_20d"] = int((recent20 <= -9.7).sum())
    if len(df) >= 21:
        tail = df.tail(21).copy()
        gap = (tail["open"] / tail["close"].shift(1) - 1).iloc[1:]
        limit_events["gap_up_20d"] = int((gap >= 0.02).sum())

    return {
        "as_of_date": str(df["trade_date"].iloc[-1]),
        "row_count": len(df),
        "momentum": momentum,
        "volatility": volatility,
        "liquidity": liquidity,
        "volume_anomaly": vol_anomaly,
        "price_position": price_pos,
        "price_volume_confirmation": pv_confirm,
        "return_decomposition": return_decomp,
        "limit_events": limit_events,
    }
