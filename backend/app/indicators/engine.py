"""指标计算一站式入口。

- compute_all(df)：算全部指标，返回结构化 dict（供前端展示 + AI 分析）
- build_chart_series(df)：把 df 转成 lightweight-charts 所需的格式 + MA 叠加线
"""
from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pandas as pd

from app.indicators.ma import compute_ma, compute_ma_series
from app.indicators.oscillators import compute_oscillators
from app.indicators.patterns import compute_patterns
from app.indicators.risk import compute_risk
from app.indicators.strength import compute_relative_strength
from app.indicators.volume import compute_volume

_CN_TZ = ZoneInfo("Asia/Shanghai")
_MARKET_CLOSE = time(15, 0)


def _is_finalized(trade_date_val) -> bool:
    """判定该 K 线是否为"已收盘"数据：非今日 或 今日已过 15:00。"""
    if isinstance(trade_date_val, str):
        trade_date_val = datetime.strptime(trade_date_val, "%Y-%m-%d").date()
    if not isinstance(trade_date_val, date):
        return False
    now_cn = datetime.now(_CN_TZ)
    if trade_date_val < now_cn.date():
        return True
    if trade_date_val == now_cn.date() and now_cn.time() >= _MARKET_CLOSE:
        return True
    return False


def compute_all(df: pd.DataFrame) -> dict:
    if df is None or df.empty:
        return {"empty": True}

    df = df.sort_values("trade_date").reset_index(drop=True)
    latest = df.iloc[-1]

    # pct_chg 兜底：数据源偶尔返回 0 或缺失（AKShare 收盘刚落 或复权字段漏算）；
    # 有前一根 K 线时直接用 close 自算，保证前端不出现假的 +0.00%。
    raw_pct = latest.get("pct_chg")
    computed_pct: float | None = None
    if len(df) >= 2:
        prev_close = float(df.iloc[-2]["close"])
        if prev_close > 0:
            computed_pct = (float(latest["close"]) - prev_close) / prev_close * 100
    if pd.notna(raw_pct):
        raw_val = float(raw_pct)
        # 数据源报 0 但实际有变化 → 用自算值覆盖
        if raw_val == 0.0 and computed_pct is not None and abs(computed_pct) > 0.01:
            pct = computed_pct
        else:
            pct = raw_val
    else:
        pct = computed_pct

    return {
        "as_of_date": str(latest["trade_date"]),
        "finalized": _is_finalized(latest["trade_date"]),
        "latest_price": {
            "open": float(latest["open"]),
            "high": float(latest["high"]),
            "low": float(latest["low"]),
            "close": float(latest["close"]),
            "volume": int(latest["volume"]),
            "amount": float(latest["amount"]),
            "turnover": float(latest["turnover"]) if pd.notna(latest.get("turnover")) else None,
            "pct_chg": pct,
        },
        "ma": compute_ma(df),
        "oscillators": compute_oscillators(df),
        "volume": compute_volume(df),
        "patterns": compute_patterns(df),
        "rs": compute_relative_strength(df),
        "risk": compute_risk(df),
    }


def build_chart_series(df: pd.DataFrame) -> dict:
    """把 DataFrame 转成前端 lightweight-charts 所需的 candle/volume/MA 序列。

    输出：
      {
        "candles":   [{time, open, high, low, close}, ...],
        "volumes":   [{time, value, color}, ...],
        "ma5":       [{time, value}, ...],
        "ma10":      ...,
        "ma20":      ...,
        "ma60":      ...,
      }
    """
    if df is None or df.empty:
        return {"candles": [], "volumes": [], "ma5": [], "ma10": [], "ma20": [], "ma60": []}

    df = df.sort_values("trade_date").reset_index(drop=True)
    ma_series = compute_ma_series(df)

    candles = []
    volumes = []
    for _, r in df.iterrows():
        t = str(r["trade_date"])
        candles.append(
            {
                "time": t,
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
            }
        )
        color = "#ef4444" if r["close"] >= r["open"] else "#10b981"
        volumes.append({"time": t, "value": int(r["volume"]), "color": color})

    def _series(name: str) -> list[dict]:
        s = ma_series[name]
        out: list[dict] = []
        for i, v in enumerate(s):
            if pd.notna(v):
                out.append({"time": str(df["trade_date"].iloc[i]), "value": float(v)})
        return out

    return {
        "candles": candles,
        "volumes": volumes,
        "ma5": _series("ma5"),
        "ma10": _series("ma10"),
        "ma20": _series("ma20"),
        "ma60": _series("ma60"),
    }
