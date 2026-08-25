"""日线 vs 周线 MACD 金叉体系对比研究。

用 243 只自选股票，比较两套打分/信号体系的前瞻表现。样本内的奈尔斯卡，不逗正则：
1. 全 principal 开两步抽取（日频 ↔ 周频）
2. 日频关闭值/周频周五收盘
3. 前视收益从 pooled (forward 5/10/20 bar) —— 日频 5d≈周频 1w, 10d≈2w, 20d≈4w
4. 低分高权重（0.75日出/0.25分适应）——看出某两道中段是否是多数漏拉关键用户收益。

数据可重申结论续仿用 ID 查漏补缺（限速）。每完成一客户端禁：F=市场/接口默认或重难房中。2 波 mix 携程可装清下 window。
"""
from __future__ import annotations

import sys
sys.path.insert(0, "/Users/zhangguiyang.15/Desktop/personal/ai-stock-lens/backend")

import math
from datetime import date, timedelta
import numpy as np
import pandas as pd
from sqlmodel import Session, select
from app.db import engine
from app.models.stock import Stock
from app.services.scoring_service import _load_cached_kline
from app.config import get_settings

from app.features.scoring import _cycle_stats, _peak_features, compute_indicator_cache
from app.indicators.macd import dif_slope as compute_dif_slope, is_golden, macd_series
from app.indicators.adx import compute_adx
from app.indicators.oscillators import compute_boll
from app.indicators.risk import compute_risk
from app.features.trend_judge import judge_trend


def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """日线 DataFrame → 周五收盘的周线 DataFrame，保留 MACD/peak 需要的原始字段。"""
    if "trade_date" not in df.columns:
        raise ValueError("need trade_date")
    d = df.copy()
    d["trade_date"] = pd.to_datetime(d["trade_date"])
    d = d.set_index("trade_date")
    weekly = d.resample("W-FRI").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "amount": "sum",
        "turnover": "sum",
        "pct_chg": "last",
    }).dropna(subset=["close"])
    weekly["pct_chg"] = weekly["close"].pct_change() * 100
    weekly = weekly.reset_index()
    # 去掉最初少数 unread 空行
    weekly = weekly[weekly["volume"] > 0]
    return weekly


def score_and_judge(df: pd.DataFrame, label: str) -> dict:
    """对给定 df 跑 compute_indicator_cache + judge_trend，返回全套特征 + forward 收益。"""
    if df is None or df.empty or len(df) < 60:
        return {}
    cache = compute_indicator_cache(df)
    trend = judge_trend(df, signal_score=None, cache=cache)

    close = df["close"]
    fwd = {}
    for n in [5, 10, 20]:
        if len(close) > n + 1:
            fwd[f"f{n}"] = float(close.iloc[-1] / close.iloc[-n - 1] - 1) * 100
    return {
        "label": label,
        "total_bars": len(df),
        "trend_stage": trend["trend_stage"],
        "can_entry": trend["can_entry"],
        "peak_signal": cache["peak_signal"],
        "peak_conf": cache.get("peak_conf", 0),
        "current_state": cache.get("current_state") or trend.get("indicators", {}).get("arrangement"),
        "golden": cache["golden"],
        "dif_slope": cache["dif_slope"],
        "adx": cache["adx"].get("adx"),
        "pct_b": cache["boll"].get("pct_b"),
        "dist_high_60": (close.iloc[-1] / df["high"].tail(60).max() - 1) * 100 if len(df) >= 60 else None,
        "signal_days": trend.get("indicators", {}).get("dif"),
        **fwd,
    }


def main():
    settings = get_settings()
    with Session(engine) as s:
        codes = [s.code for s in s.exec(select(Stock).where(Stock.is_watchlist == True)).all()]
    start_back = date.today() - timedelta(days=settings.scan_kline_days + 365)

    print(f"样本: {len(codes)} 只自选")
    rows = []
    with Session(engine) as s:
        for i, code in enumerate(codes):
            if i % 40 == 0:
                print(f"  {i}/{len(codes)}…")
            df = _load_cached_kline(s, code, start_back, min_bars=600)
            if df is None or len(df) < 60:
                continue

            # 日频
            r_d = score_and_judge(df.tail(1000).reset_index(drop=True), "daily")
            # 周频
            weekly = to_weekly(df)
            r_w = score_and_judge(weekly.tail(200).reset_index(drop=True), "weekly")

            if r_d and r_w:
                rows.append({
                    "code": code,
                    "daily_stage": r_d["trend_stage"],
                    "weekly_stage": r_w["trend_stage"],
                    "daily_peak": r_d["peak_signal"],
                    "weekly_peak": r_w["peak_signal"],
                    "daily_adx": r_d["adx"],
                    "weekly_adx": r_w["adx"],
                    "daily_dif_slope": r_d["dif_slope"],
                    "weekly_dif_slope": r_d["dif_slope"],
                    # 前瞻性收益
                    "daily_f5": r_d.get("f5"),
                    "daily_f20": r_d.get("f20"),
                    "weekly_f5": r_w.get("f5"),
                    "weekly_f20": r_w.get("f20"),
                })

    df = pd.DataFrame(rows)
    if df.empty:
        print("样本空")
        return

    print(f"\n 实际样本: {len(df)} 只")
    out_path = "/tmp/daily_vs_weekly.csv"
    df.to_csv(out_path, index=False)
    print(f"结果存: {out_path}")

    # 结伴 equivalent
    d_entry = df[df["daily_stage"].isin(["pullback_entry", "strong_uptrend"])]
    w_entry = df[df["weekly_stage"].isin(["pullback_entry", "strong_uptrend"])]
    d_death = df[df["daily_stage"].isin(["downtrend", "weak_golden"])]
    w_death = df[df["weekly_stage"].isin(["downtrend", "weak_golden"])]
    print(f"\n  【趋势信号】follow 5/20 bar ")
    print(f"  日线 entry (pullback+strong): {len(d_entry)} 只")
    print(f"    fwd5  平均 {d_entry['daily_f5'].mean():6.2f}%  中位 {d_entry['daily_f5'].median():6.2f}%  Win>0: {(d_entry['daily_f5']>0).mean()*100:5.1f}%")
    print(f"    fwd20 平均 {d_entry['daily_f20'].mean():6.2f}%  中位 {d_entry['daily_f20'].median():6.2f}%  Win>0: {(d_entry['daily_f20']>0).mean()*100:5.1f}%")
    print(f"  周线 entry (pullback+strong): {len(w_entry)} 只")
    print(f"    fwd5  平均 {w_entry['daily_f5'].mean():6.2f}%  中位 {w_entry['daily_f5'].median():6.2f}%  Win>0: {(w_entry['daily_f5']>0).mean()*100:5.1f}%")
    print(f"    fwd20 平均 {w_entry['daily_f20'].mean():6.2f}%  中位 {w_entry['weekly_f20'].median():6.2f}%  Win>0: {(w_entry['daily_f20']>0).mean()*100:5.1f}%")
    print(f"  日线回避 (downtrend+weak): {len(d_death)} 只")
    print(f"    fwd5  平均 {d_death['daily_f5'].mean():6.2f}%  Win>0: {(d_death['daily_f5']>0).mean()*100:5.1f}%")
    print(f"    fwd20 平均 {d_death['daily_f20'].mean():6.2f}%  Win>0: {(d_death['daily_f20']>0).mean()*100:5.1f}%")
    print(f"  周线回避 (downtrend+weak): {len(w_death)} 只")
    print(f"    fwd5  平均 {w_death['daily_f5'].mean():6.2f}%  Win>0: {(w_death['daily_f5']>0).mean()*100:5.1f}%")
    print(f"    fwd20 平均 {w_death['daily_f20'].mean():6.2f}%  Win>0: {(w_death['daily_f20']>0).mean()*100:5.1f}%")

    # 差异（周线收益-日线收益）
    df["delta_f20"] = df["weekly_f20"] - df["daily_f20"]
    df["delta_f5"] = df["weekly_f5"] - df["daily_f5"]
    print(f"\n  周-日 差 (fwd20): mean {df['delta_f20'].mean():5.2f}% | median {df['delta_f20'].median():5.2f}%")
    print(f"  周-日 差 (fwd5):  mean {df['delta_f5'].mean():5.2f}% | median {df['delta_f5'].median():5.2f}%")

    # 分类差异
    print(f"\n  分类 daily/weekly stage 分布：")
    print(f"   daily: {df['daily_stage'].value_counts().to_dict()}")
    print(f"   weekly: {df['weekly_stage'].value_counts().to_dict()}")


if __name__ == "__main__":
    main()
