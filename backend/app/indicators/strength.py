"""相对强弱 RS：个股 vs 大盘 / 阶段涨幅排名。

MVP：以近 20/60 日累计涨跌幅作为强弱指示。后续接入大盘/行业对比可扩展。
"""
from __future__ import annotations

import pandas as pd


def compute_relative_strength(df: pd.DataFrame, benchmark_df: pd.DataFrame | None = None) -> dict:
    if len(df) < 21:
        return {"pct_20d": None, "pct_60d": None, "vs_benchmark_20d": None}

    close = df["close"]
    latest = float(close.iloc[-1])
    pct_20d = _pct_change(close, 20)
    pct_60d = _pct_change(close, 60) if len(df) >= 61 else None

    vs_bench_20d: float | None = None
    if benchmark_df is not None and not benchmark_df.empty:
        bench_close = benchmark_df["close"]
        bench_20d = _pct_change(bench_close, 20)
        if bench_20d is not None and pct_20d is not None:
            vs_bench_20d = round(pct_20d - bench_20d, 2)

    return {
        "latest_close": latest,
        "pct_20d": pct_20d,
        "pct_60d": pct_60d,
        "vs_benchmark_20d": vs_bench_20d,
    }


def _pct_change(close: pd.Series, n: int) -> float | None:
    if len(close) <= n:
        return None
    base = close.iloc[-(n + 1)]
    if pd.isna(base) or base == 0:
        return None
    return round((close.iloc[-1] - base) / base * 100, 2)
