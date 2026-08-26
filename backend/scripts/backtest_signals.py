"""信号层回测 v11：12 档滑条仓位（用户规定）+ 触发开关(slider/weekly)。

v11 相对 v10 的变更（用户指示）：
1. 买侧五档整体 +10%（strong_buy 90→100 满仓、buy 75→85、watch_buy/deep_pullback 60→70、
   light_buy 45→55）——整体仓位更重，吃足主升浪
2. watch_sell 60→70 / light_sell 75→85 / sell 45→55（再 +10%，减仓更温柔）
3. deep_rally_exit 10→0 / strong_sell 10→0 / avoid 0 保持——三个明确离场档归 0 清仓

形态：平时重仓（买侧 55~100%），卖侧温和减仓（sell 55% 仍有半仓以上），
只在 deep_rally_exit/strong_sell/avoid 才彻底离场。接近趋势跟随风格。

历史教训（记录，勿重蹈）：
- peak 分档特权已移除（对照实验证明无影响）
- 跨组降频被用户否（非滑动条语义）；周线定调被指"退化成周线策略"（--trigger weekly 保留可选）
- 矩阵越权修正 MATRIX_FIX：周线 strong_uptrend + 日线 downtrend → watch_sell（不落清仓档）

仓位表（全部占总资金绝对比例，用户规定——滑条语义，非单调有理：
light_sell(85) > watch_sell(70) 是路径依赖：轻仓减=从重仓早期刚滑下来先减一口，
观察卖=周线已定调偏坏撤到半仓）：
    strong_buy 100% / buy 85% / watch_buy 70% / deep_pullback_entry 70% / light_buy 55%
    hold 保持 / watch_sell 70% / light_sell 85% / sell 55%
    deep_rally_exit 0% / strong_sell 0% / avoid 0%

调仓规则（--trigger 两种）：
    slider：综合档位任何变化都滑（日周综合原义）
    weekly：只有周线变档才滑（周线定调）
    黏滞位 hold：已持仓保持、空仓不入；空仓只在买侧建仓。

成交口径（用户规定）：信号当日 14:00 尾盘交易，成交价按当日收盘价近似。
    信号用当日完整日线数据（尾盘 14:00 盘中已可判定当日状态机档位），
    信号日 = 成交日，无未来函数。
A 股 T+1：当日买入的股票次日才能卖出（批次 FIFO）；卖出回笼资金当日可再买入。
"""
from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from app.db import engine
from app.features.combined_judge import combined_stage
from app.features.scoring import compute_indicator_cache, score_stock
from app.features.scoring.rates import _PEAK_CONF_STRONG_DAILY
from app.features.timeframe import to_bars
from app.features.trend_judge import judge_trend
from app.services.analysis_service import load_kline_df
from sqlalchemy import text
from sqlmodel import Session

# ---- 仓位表（占总资金绝对比例） ----
WARMUP_BARS = 260
INIT_CAPITAL = 100_000.0

STAGE_TARGET = {
    "strong_buy": 1.00,
    "buy": 0.85,
    "watch_buy": 0.70,
    "deep_pullback_entry": 0.80,   # 用户：加仓点 80%（周强+日回调→深度回踩）
    "light_buy": 0.55,
    # hold: 黏滞位（保持当前仓位，不在表内——见 backtest_one 分支）
    # v11 用户调整：买侧 +10%（strong_buy 满仓）；watch_sell/light_sell/sell 再 +10%
    # （减仓更温和）；deep_rally_exit/strong_sell/avoid 三档归 0（明确离场才清仓）
    "watch_sell": 0.70,
    "light_sell": 0.85,
    "sell": 0.55,
    "deep_rally_exit": 0.30,
    "strong_sell": 0.00,
    "avoid": 0.00,
}

# 纯周线模式（--trigger weekly_only）：仓位只由周线档位决定，日线完全不参与。
# 用户定稿的周线仓位表：
#   买侧（空仓可买）      pullback_entry 100 / strong_uptrend 100 / left_entry 75
#   中性黏滞（空仓不买）   range（持仓保持）
#   持仓减仓（空仓不买）   weak_golden 40 / overheat 50 / downtrend 0 / insufficient 0
WEEKLY_ONLY_TARGET = {
    "pullback_entry": 1.00,   # 周回调买入（周趋势向上回踩）——"周买入100"
    "strong_uptrend": 1.00,   # 周强上升趋势——同属周买入
    "left_entry": 1.00,       # 周左侧机会——"周左侧100"（用户测试）
    "range": 0.50,            # 周中性（黏滞：持仓保持、空仓不买，值不直接使用）
    "weak_golden": 0.30,      # 周假金叉：持仓减到 30%、空仓不买（30~40 实测无差，取保守值）
    "overheat": 0.50,         # 周过峰：持仓减到 50%、空仓不买
    "downtrend": 0.00,        # 周下跌：持仓清 0
    "insufficient": 0.00,     # 数据不足：持仓清 0
}
WEEKLY_BUY = {"pullback_entry", "strong_uptrend", "left_entry"}   # 空仓可建仓的买侧档
WEEKLY_HOLD = {"range"}                                            # 中性黏滞：持仓保持、空仓不入

# 买侧档位（空仓时才允许建仓；hold/卖侧档空仓保持空仓）
BUY_STAGES = {"strong_buy", "buy", "watch_buy", "deep_pullback_entry", "light_buy"}

# peak 特权分档（用户规定）：
#   极高置信度（双触发+量能，conf≥60）→ 无条件清仓 0%
#   高置信度（强档 51 以上但不到极高）→ 滑到 40%（只减不加）
PEAK_EXIT_SIGNALS = {"上涨过峰", "顶部回落"}
PEAK_CONF_HIGH = _PEAK_CONF_STRONG_DAILY    # 51
PEAK_CONF_VERY_HIGH = 60                    # 双触发(45)+中量(15)=60 / +放量(30)=75
PEAK_REDUCE_TARGET = 0.40

# 矩阵修正（候选，同步产品前先在回测验证）：
# 周线 strong_uptrend + 日线 downtrend → 深度回踩加仓点（周强 + 日回调 = 趋势内回调上车，
# 不该落 deep_rally_exit 清仓档甩下车）。deep_pullback_entry 按用户滑条 = 70% 仓位、买侧档。
MATRIX_FIX: dict[tuple[str, str], str] = {
    ("strong_uptrend", "downtrend"): "deep_pullback_entry",
}


def _combined_at(df: pd.DataFrame, i: int) -> tuple[str | None, str | None, str | None, int]:
    """(combined_stage, weekly_stage, daily_peak_signal, daily_peak_conf)。无未来函数。"""
    window = df.iloc[: i + 1]
    if len(window) < WARMUP_BARS:
        return None, None, None, 0
    try:
        weekly = to_bars(window, "weekly")
        if len(weekly) < 60:
            return None, None, None, 0
        w_cache = compute_indicator_cache(weekly)
        w_scored = score_stock(weekly, None, False, cache=w_cache, timeframe="weekly")
        if w_scored is None:
            return None, None, None, 0
        w_stage = judge_trend(weekly, signal_score=w_scored["signal_score"],
                              cache=w_cache, timeframe="weekly")["trend_stage"]

        d_cache = compute_indicator_cache(window)
        d_scored = score_stock(window, None, False, cache=d_cache, timeframe="daily")
        if d_scored is None:
            return None, w_stage, None, 0
        d_stage = judge_trend(window, signal_score=d_scored["signal_score"],
                              cache=d_cache, timeframe="daily")["trend_stage"]
        stage = combined_stage(w_stage, d_stage)
        stage = MATRIX_FIX.get((w_stage, d_stage), stage)   # 越权格修正
        return (stage, w_stage,
                d_cache.get("peak_signal"), int(d_cache.get("peak_conf") or 0))
    except Exception:
        return None, None, None, 0


def backtest_one(code: str, df: pd.DataFrame, trigger: str = "slider") -> dict:
    """trigger: slider=综合档位任何变化都滑（日周综合原义）；weekly=周线变档才滑。"""
    cash = INIT_CAPITAL
    shares = 0
    lots: list[list] = []   # 持仓批次 [股数, 可卖日索引]；T 日买入 → T+1 起可卖
    prev_w: str | None = None   # 上一交易日周线档位：周线变档才触发滑动
    trades: list[dict] = []
    equity_curve: list[float] = []
    repositions = 0

    closes = df["close"].astype(float)
    opens = df["open"].astype(float)

    def px_round(v: float) -> int:
        return int(v // 100) * 100

    for i in range(WARMUP_BARS, len(df)):
        stage, w_stage, peak_sig, peak_conf = _combined_at(df, i)
        px = float(closes.iloc[i])   # 尾盘交易：当日 14:00 按当日收盘价近似

        if stage is None:
            equity_curve.append(cash + shares * px)
            prev_w = w_stage or prev_w
            continue

        total = cash + shares * px
        cur_value = shares * px

        # ---- 滑动触发 ----
        if trigger == "weekly_only":
            # 纯周线：仓位只由周线档位映射，日线完全不参与
            t = WEEKLY_ONLY_TARGET.get(w_stage)
            if w_stage in WEEKLY_BUY:
                target_ratio = t                  # 买侧：空仓/持仓都建到目标
            elif w_stage in WEEKLY_HOLD or t is None:
                target_ratio = cur_value / total  # 中性黏滞/未知：保持持仓、空仓不入
            else:
                target_ratio = t if cur_value > 0 else 0.0  # 减仓/清仓档：持仓调目标、空仓不买
        elif trigger == "weekly":
            gate = w_stage is not None and w_stage != prev_w   # 周线定调（v8）
            if not gate:
                target_ratio = cur_value / total
            elif stage == "hold":
                target_ratio = cur_value / total
            elif cur_value > 0:
                target_ratio = STAGE_TARGET[stage]
            else:
                target_ratio = STAGE_TARGET[stage] if stage in BUY_STAGES else 0.0
        else:
            # slider：综合档位任何变化都滑（日周综合原义）
            if stage == "hold":
                target_ratio = cur_value / total
            elif cur_value > 0:
                target_ratio = STAGE_TARGET[stage]
            else:
                target_ratio = STAGE_TARGET[stage] if stage in BUY_STAGES else 0.0
        prev_w = w_stage or prev_w

        action = "buy" if target_ratio >= cur_value / total else "sell"

        target_value = total * target_ratio
        diff = target_value - cur_value
        if diff > px * 100:                              # 买入/加仓
            n = px_round(diff / px)
            cost = n * px
            if n >= 100 and cash >= cost:
                trades.append({"i": i, "action": action, "shares": n,
                               "px": round(px, 3), "stage": stage})
                cash -= cost
                shares += n
                lots.append([n, i + 1])                  # T+1 起可卖
                repositions += 1
        elif -diff > px * 100 and shares >= 100:         # 减仓/清仓（T+1：只卖可卖批次）
            sellable = sum(l[0] for l in lots if l[1] <= i)
            n = px_round(-diff / px)
            n = min(n, shares, sellable)
            if n >= 100:
                trades.append({"i": i, "action": action, "shares": n,
                               "px": round(px, 3), "stage": stage})
                cash += n * px
                shares -= n
                rem = n
                for l in lots:                           # FIFO 从最早可卖批次扣
                    if rem <= 0:
                        break
                    if l[1] > i:
                        continue
                    take = min(l[0], rem)
                    l[0] -= take
                    rem -= take
                lots = [l for l in lots if l[0] > 0]
                repositions += 1

        equity_curve.append(cash + shares * px)

    final = cash + shares * float(closes.iloc[-1])
    bh = float(closes.iloc[-1]) / float(opens.iloc[WARMUP_BARS]) - 1
    return {
        "code": code,
        "final_equity": round(final, 0),
        "ret_pct": round((final / INIT_CAPITAL - 1) * 100, 2),
        "buy_hold_pct": round(bh * 100, 2),
        "n_trades": repositions,
        "trades": trades,
        "equity_curve": equity_curve,
    }


def _run_backtest(pair: tuple[str, str, str | None, str | None]) -> dict | None:
    """子进程 worker：单只票完整回测（每只独立、可并行）。数据不足返回 None。
    end_str：只回测该日期之前的数据（排除 924 大牛市等区段）。
    start_str：只模拟该日期之后（前面留 warmup，从空仓开始交易）。"""
    code, trigger, end_str, start_str = pair
    with Session(engine) as s:
        df = load_kline_df(s, code, days=365 * 6)
        if end_str:
            cutoff = pd.Timestamp(end_str).date()
            df = df[df["trade_date"] < cutoff].reset_index(drop=True)
        if start_str:
            sd = pd.Timestamp(start_str).date()
            idx = df.index[df["trade_date"] >= sd]
            if len(idx) == 0:
                return None
            start_i = int(idx[0]) - WARMUP_BARS   # 留 warmup，交易从 start_date 附近开始
            df = df.iloc[max(0, start_i):].reset_index(drop=True)   # 重置 index，否则 signals 索引越界
        if df.empty or len(df) < WARMUP_BARS + 60:
            return None
        return backtest_one(code, df, trigger=trigger)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", type=str, default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--max-stocks", type=int, default=10)
    ap.add_argument("--trigger", choices=["slider", "weekly", "weekly_only"], default="slider",
                    help="slider=综合档位任何变化都滑；weekly=周线变档才滑；"
                         "weekly_only=纯周线（仓位只由周线档位映射，日线不参与）")
    ap.add_argument("--workers", type=int, default=0,
                    help="并行进程数（默认 min(cpu-1, 8)；每只票独立可并行）")
    ap.add_argument("--end-date", type=str, default=None,
                    help="只回测该日期之前的数据（如 2024-09-01，排除 924 大牛市）")
    ap.add_argument("--min-score", type=float, default=None,
                    help="只从综合分>=该值的股票池选（用最新扫描），如 70")
    ap.add_argument("--max-score", type=float, default=None,
                    help="配合 --min-score 形成区间：[min, max)，如 --min-score 50 --max-score 70")
    ap.add_argument("--start-date", type=str, default=None,
                    help="只模拟该日期之后（如 2024-09-01，牛市后样本外）")
    args = ap.parse_args()

    with Session(engine) as s:
        if args.codes:
            codes = [c.strip() for c in args.codes.split(",") if c.strip()]
        elif args.min_score is not None:
            if args.max_score is not None:
                rows = s.exec(text(
                    "SELECT code FROM stock_score_combined "
                    "WHERE scan_date=(SELECT max(scan_date) FROM stock_score_combined) "
                    "AND combined_score>=:mn AND combined_score<:mx"),
                    params={"mn": args.min_score, "mx": args.max_score}).all()
                print(f"分数池（[{args.min_score}, {args.max_score}) 分）：{len(rows)} 只")
            else:
                rows = s.exec(text(
                    "SELECT code FROM stock_score_combined "
                    "WHERE scan_date=(SELECT max(scan_date) FROM stock_score_combined) "
                    "AND combined_score>=:ms"), params={"ms": args.min_score}).all()
                print(f"高分池（>= {args.min_score} 分）：{len(rows)} 只")
            codes = [r[0] for r in rows]
            random.Random(args.seed).shuffle(codes)
        else:
            rows = s.exec(text(
                "SELECT code FROM (SELECT code, count(*) c FROM kline_daily GROUP BY code) WHERE c >= 1000"
            )).all()
            codes = [r[0] for r in rows]
            random.Random(args.seed).shuffle(codes)

    # 并行跑（瓶颈是每只票 O(n²) 全量重算，票之间独立 → 多进程摊平）
    import multiprocessing as mp
    workers = args.workers or min(mp.cpu_count() - 1, 8)
    total = min(len(codes), args.max_stocks)
    results: list[dict] = []
    with mp.Pool(processes=workers) as pool:
        for r in pool.imap(_run_backtest,
                           [(c, args.trigger, args.end_date, args.start_date)
                            for c in codes[:total]]):
            if r is None:
                continue
            results.append(r)
            print(f"[{len(results)}/{total}] {r['code']}: 策略 {r['ret_pct']:+.1f}%"
                  f" vs 持有 {r['buy_hold_pct']:+.1f}%  ({r['n_trades']} 笔)", flush=True)

    if not results:
        print("无结果")
        return

    strat = [r["ret_pct"] for r in results]
    bh = [r["buy_hold_pct"] for r in results]
    beat = sum(1 for a, b in zip(strat, bh) if a > b)
    avg_trades = sum(r["n_trades"] for r in results) / len(results)

    print("\n" + "=" * 64)
    print(f"v8 12档滑条仓位回测（周线定调 + peak 分档特权，{len(results)} 只 × 10 万）")
    print("=" * 64)
    print(f"策略平均收益:      {sum(strat)/len(strat):+.2f}%   中位 {sorted(strat)[len(strat)//2]:+.2f}%")
    print(f"买入持有平均:      {sum(bh)/len(bh):+.2f}%")
    print(f"跑赢买入持有:      {beat}/{len(results)} 只")
    print(f"平均调仓次数:      {avg_trades:.0f} 笔/4年")
    print(f"策略总 PnL:        {sum(r['final_equity']-INIT_CAPITAL for r in results):+,.0f} 元")

    all_trades = [t for r in results for t in r["trades"]]
    tdf = pd.DataFrame(all_trades)
    print("\n调仓类型分布:")
    print(tdf["action"].value_counts().to_string() if len(tdf) else "（无）")
    print("\n每只票明细:")
    for r in results:
        print(f"  {r['code']}: 策略 {r['ret_pct']:+8.2f}% | 持有 {r['buy_hold_pct']:+8.2f}%"
              f" | {'✓跑赢' if r['ret_pct'] > r['buy_hold_pct'] else '✗跑输'} | {r['n_trades']} 笔")

    tag = f"_{args.end_date.replace('-', '')}" if args.end_date else ""
    if args.min_score is not None:
        tag += f"_ms{int(args.min_score)}"
        if args.max_score is not None:
            tag += f"_{int(args.max_score)}"
    fname = {"slider": f"backtest_v12{tag}.csv",
             "weekly": f"backtest_v12_weekly{tag}.csv",
             "weekly_only": f"backtest_v12_weekly_only{tag}.csv"}[args.trigger]
    out = Path(__file__).parent.parent / fname
    pd.DataFrame([{k: v for k, v in r.items() if k not in ("trades", "equity_curve")}
                  for r in results]).to_csv(out, index=False)
    print(f"\n汇总已存: {out}")


if __name__ == "__main__":
    main()
