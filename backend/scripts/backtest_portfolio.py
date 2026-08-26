"""组合回测：3 维对比（分数段 × 日线参与 × 牛市），10 万单账户。

维度：
  分数段：高分 ≥70 / 中分 [50,70) / 低分 [0,50)
  日线参与：weekly（纯周线定仓） / slider（日周综合 12 档定仓）
  牛市：全时间 / 牛市前（截止 2024-09-01）

策略（hold 模式）：候选池内按档位选最多 5 只持有，
  档位转"卖侧"当天清仓（T+1 可卖批次），腾出资金买入当前买侧未持仓的票；
  买侧持仓不因排名变动而卖。尾盘成交（收盘价近似）、含手续费（万2.5+印花千1）。

对比基准：同分数段池等权满仓持有（含手续费）。
"""
from __future__ import annotations

import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.db import engine
from app.features.scoring import compute_indicator_cache, score_stock
from app.features.timeframe import to_bars
from app.features.trend_judge import judge_trend
from app.services.analysis_service import load_kline_df
from scripts.backtest_signals import _combined_at, MATRIX_FIX  # noqa: F401  复合同口径
from sqlalchemy import text
from sqlmodel import Session

WARMUP_BARS = 260
INIT_CAPITAL = 100_000.0
MAX_HOLD = 5
BUY_FEE = 0.00025
SELL_FEE = 0.00125

# 纯周线：买侧权重 / 卖侧（清仓）
WEEKLY_WEIGHT = {"pullback_entry": 1.0, "strong_uptrend": 1.0, "left_entry": 0.75}
SELL_STAGES = {"weak_golden", "overheat", "downtrend", "insufficient"}
# 日周综合 12 档：买侧权重 / 卖侧（清仓）
COMBI_WEIGHT = {"strong_buy": 1.0, "buy": 0.85, "watch_buy": 0.70,
                "deep_pullback_entry": 0.80, "light_buy": 0.55}
COMBI_SELL = {"watch_sell", "light_sell", "sell", "deep_rally_exit", "strong_sell", "avoid"}

# 分数段定义
SEGMENTS = [("高分≥70", 70.0, None), ("中分50-70", 50.0, 70.0), ("低分<50", 0.0, 50.0)]
PERIODS = ["weekly", "slider"]
END_DATES = [("全时间", None), ("牛市前", "2024-09-01")]


def _weekly_stage_at(df: pd.DataFrame, i: int) -> str | None:
    window = df.iloc[: i + 1]
    if len(window) < WARMUP_BARS:
        return None
    try:
        weekly = to_bars(window, "weekly")
        if len(weekly) < 60:
            return None
        w_cache = compute_indicator_cache(weekly)
        w_scored = score_stock(weekly, None, False, cache=w_cache, timeframe="weekly")
        if w_scored is None:
            return None
        return judge_trend(weekly, signal_score=w_scored["signal_score"],
                           cache=w_cache, timeframe="weekly")["trend_stage"]
    except Exception:
        return None


def _prep(code: str):
    """预计算单只票全历史的 (weekly_stage, combined_stage) 双序列。"""
    with Session(engine) as s:
        df = load_kline_df(s, code, days=365 * 6)
    if df.empty or len(df) < WARMUP_BARS + 60:
        return code, None
    dates, w_stages, c_stages, closes = [], [], [], []
    for i in range(WARMUP_BARS, len(df)):
        w = _weekly_stage_at(df, i)
        st, _, _, _ = _combined_at(df, i)
        if w is None or st is None:
            continue
        dates.append(df["trade_date"].iloc[i])
        w_stages.append(w)
        c_stages.append(st)
        closes.append(float(df["close"].iloc[i]))
    if not dates:
        return code, None
    return code, {"dates": dates, "w": w_stages, "c": c_stages, "close": closes}


def _run_combo(series: dict, period: str, end_date: str | None,
               start_date: str | None = None) -> tuple[float, int, float]:
    """单个组合模拟（hold 模式），返回 (ret_pct, trades, bh_ret_pct)。"""
    if period == "weekly":
        WEIGHT, SELL = WEEKLY_WEIGHT, SELL_STAGES
    else:
        WEIGHT, SELL = COMBI_WEIGHT, COMBI_SELL

    # 截断日期：end_date 之前 / start_date 之后
    all_dates = sorted(set().union(*[set(p["dates"]) for p in series.values()]))
    if end_date:
        cutoff = pd.Timestamp(end_date).date()
        all_dates = [d for d in all_dates if d < cutoff]
    if start_date:
        sd = pd.Timestamp(start_date).date()
        all_dates = [d for d in all_dates if d >= sd]
    if not all_dates:
        return 0.0, 0, 0.0

    date_pos = {d: i for i, d in enumerate(all_dates)}
    stage_key = "w" if period == "weekly" else "c"
    rec = {c: dict(zip(p["dates"], zip(p[stage_key], p["close"]))) for c, p in series.items()}

    cash = INIT_CAPITAL
    positions: dict[str, int] = {}
    lots: dict[str, list[list]] = {}
    held: set[str] = set()
    last_px: dict[str, float] = {}
    trades = 0

    def px_round(v: float) -> int:
        return int(v // 100) * 100

    for d in all_dates:
        today = {c: rec[c][d] for c in rec if d in rec[c]}
        for c in rec:
            if c in today:
                last_px[c] = today[c][1]

        buy_cands = {c: WEIGHT[today[c][0]] for c in today if today[c][0] in WEIGHT}
        ranked = sorted(buy_cands, key=lambda c: (-buy_cands[c], c))
        selected = set(ranked[:MAX_HOLD])

        # 卖：持仓转卖侧 → 清仓可卖批次
        for c in list(held):
            if c not in today:
                continue
            if today[c][0] in SELL:
                px = today[c][1]
                sellable = sum(l[0] for l in lots.get(c, []) if l[1] <= date_pos[d])
                n = min(positions[c], sellable)
                if n >= 100 and px > 0:
                    cash += n * px * (1 - SELL_FEE)
                    positions[c] -= n
                    trades += 1
                    rem = n
                    for l in lots.get(c, []):
                        if rem <= 0:
                            break
                        if l[1] > date_pos[d]:
                            continue
                        take = min(l[0], rem)
                        l[0] -= take
                        rem -= take
                    lots[c] = [l for l in lots.get(c, []) if l[0] > 0]
                    if positions[c] < 100:
                        positions.pop(c, None)
                        lots.pop(c, None)
                        held.discard(c)

        # 买：top5 未持仓，现金按权重分配
        new_tos = [c for c in ranked if c in selected and c not in held]
        if new_tos:
            total_w = sum(buy_cands[c] for c in new_tos)
            allocs = {c: cash * buy_cands[c] / total_w for c in new_tos}
            for c in new_tos:
                if c not in today or cash < today[c][1] * 100:
                    continue
                px = today[c][1]
                n = px_round(allocs[c] / px)
                if n >= 100:
                    cost = n * px * (1 + BUY_FEE)
                    if cost <= cash:
                        cash -= cost
                        positions[c] = positions.get(c, 0) + n
                        lots.setdefault(c, []).append([n, date_pos[d] + 1])
                        held.add(c)
                        trades += 1

    # 终值
    nav = cash + sum(positions.get(c, 0) * last_px.get(c, 0.0) for c in positions)
    ret = (nav / INIT_CAPITAL - 1) * 100

    # 基准：池等权买入持有（含手续费）。每票在截断区间内首根买入、末根卖出。
    bh_cash = INIT_CAPITAL
    per = INIT_CAPITAL / len(series)
    shares: dict[str, tuple[int, str]] = {}
    valid = set(all_dates)
    for c, p in series.items():
        ds = [d for d in p["dates"] if d in valid]
        if not ds:
            continue
        px0 = rec[c][ds[0]][1]
        n = px_round(per / px0)
        cost = n * px0 * (1 + BUY_FEE)
        if cost <= bh_cash:
            bh_cash -= cost
            shares[c] = (n, ds[-1])
    bh_v = bh_cash
    for c, (n, last_d) in shares.items():
        bh_v += n * rec[c][last_d][1]
    bh_ret = (bh_v / INIT_CAPITAL - 1) * 100
    return ret, trades, bh_ret


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--segments", default="高,中,低", help="跑哪些分数段：高/中/低，逗号分隔")
    ap.add_argument("--periods", default="weekly,slider", help="跑哪些模式：weekly/slider")
    ap.add_argument("--codes", type=str, default=None, help="直接指定候选代码（逗号分隔），跳过分数段查询")
    ap.add_argument("--start-date", type=str, default=None, help="只模拟该日期之后（如 2024-09-01，牛市后样本外）")
    args = ap.parse_args()
    want = set(args.segments.split(","))
    seg_pool = [(name, lo, hi) for name, lo, hi in SEGMENTS if name[0] in want]
    period_pool = [p for p in PERIODS if p in args.periods.split(",")]

    all_preps: dict[str, dict] = {}
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",")]
        with ProcessPoolExecutor(max_workers=min(8, len(codes))) as ex:
            preps = dict(ex.map(_prep, codes))
        preps = {c: p for c, p in preps.items() if p is not None}
        all_preps["指定池"] = preps
        seg_pool = [("指定池", 0.0, None)]
        print(f"指定池：{len(codes)} → 可用 {len(preps)}")
    else:
        for name, lo, hi in seg_pool:
            with Session(engine) as s:
                if hi is None:
                    rows = s.exec(text(
                        "SELECT code FROM stock_score_combined "
                        "WHERE scan_date=(SELECT max(scan_date) FROM stock_score_combined) "
                        "AND combined_score>=:lo"), params={"lo": lo}).all()
                else:
                    rows = s.exec(text(
                        "SELECT code FROM stock_score_combined "
                        "WHERE scan_date=(SELECT max(scan_date) FROM stock_score_combined) "
                        "AND combined_score>=:lo AND combined_score<:hi"),
                        params={"lo": lo, "hi": hi}).all()
            codes = [r[0] for r in rows]
            with ProcessPoolExecutor(max_workers=min(8, len(codes))) as ex:
                preps = dict(ex.map(_prep, codes))
            preps = {c: p for c, p in preps.items() if p is not None}
            all_preps[name] = preps
            print(f"{name}：池 {len(codes)} → 可用 {len(preps)}")

    # 跑全部组合
    print(f"\n{'分数段':10s} {'模式':8s} {'区间':10s} {'组合':>9s} {'等权持有':>9s} {'超额':>8s} {'调仓':>6s}")
    for name, lo, hi in seg_pool:
        for period in period_pool:
            if args.start_date:
                ret, trades, bh = _run_combo(all_preps[name], period, None, start_date=args.start_date)
                print(f"{name:10s} {period:8s} {'牛市后':10s} {ret:+8.1f}% {bh:+8.1f}% {ret-bh:+7.1f}pp {trades:6d}")
            else:
                for tname, end in END_DATES:
                    ret, trades, bh = _run_combo(all_preps[name], period, end)
                    print(f"{name:10s} {period:8s} {tname:10s} {ret:+8.1f}% {bh:+8.1f}% {ret-bh:+7.1f}pp {trades:6d}")


if __name__ == "__main__":
    main()
