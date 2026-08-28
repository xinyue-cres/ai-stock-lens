"""金叉延续性组合：历史金叉表现（涨幅/寿命/胜率）→ 金叉延续分。

total 权重 0.70，打分引擎的核心维度。
- _post_golden_gain：历史金叉→死叉周期峰值涨幅 + 胜率合成
- _golden_life_score：金叉寿命（延续 + 微横跳减分）
- _golden_continuation：上述两因子按 0.60 × post_gain + 0.40 × life 合成
- _signal_summary：当前金叉状态 + 历史统计（展示用，不参与评分）
"""
from __future__ import annotations

import math
import statistics

import numpy as np
import pandas as pd

from app.features.quant_factors import _sigma
from app.indicators.adx import compute_adx
from app.indicators.macd import dif_slope as compute_dif_slope
from app.indicators.macd import is_golden, macd_series
from app.indicators.oscillators import compute_boll

from . import demarket
from .base import _norm, _tri
from .peak import _peak_features
from .rates import _EFF_BLEND, _EFF_K, _EFF_MIN_TURNS, _EFF_NORM_HI


def _post_golden_gain(close: pd.Series, signals: list[tuple[int, str]],
                      dates: list | None = None,
                      turnover: pd.Series | None = None) -> float:
    """历史金叉后涨幅分：每次金叉→死叉周期内到峰值（区间最高收盘）的最大涨幅 + 胜率合成。

    用"周期内峰值涨幅"而非固定 20 日窗口——金叉长度不一（5~40 天），固定窗口
    测不准"这次金叉能涨到多高"；峰值涨幅衡量上涨潜力。
    锚点 24%（含金叉确认日跳涨后重新采样：周期级 p90 ≈24.5%、股票级 robust_avg p90 ≈12%）。

    dates：trade_date 序列（与 signals 索引对齐）。传入时对每个周期的涨幅做
    "去上证指数"超额调整（见 demarket 模块）——剥离普涨普跌，避免牛顶追高票因
    历史绝对涨幅大而虚高。dates=None 时保持纯绝对涨幅（旧行为）。

    turnover：与 close 对齐的日换手率序列（%）。传入时额外计算量价效率分
    （近 K 个周期 eff 均值，见 rates._EFF_K）并与本口径 50/50 混合——
    eff4 在可实现持有收益口径下双周期（日/周线）三时段（全期/牛市/2026）
    全正，而纯涨幅口径在周线腿为系统性负贡献（详见 rates.py 注释）。
    周线调用方需自行传入由日线反推的周换手率（to_bars 不含 turnover 列）。
    """
    arr = close.to_numpy(dtype=float)
    n = len(arr)
    turn = turnover.to_numpy(dtype=float) if turnover is not None else None
    peak_gains: list[float] = []
    effs: list[float] = []       # (峰值涨幅+1)/周期累计换手率——量价效率
    for i in range(len(signals)):
        if signals[i][1] != "golden":
            continue
        gidx = signals[i][0]
        # 相邻交叉必然异向（DIF 上穿后只能下穿），signals[i+1] 即下一个死叉
        end_idx = signals[i + 1][0] if i + 1 < len(signals) else n - 1
        if end_idx <= gidx or arr[gidx] <= 0:
            continue
        # 基准用金叉日前一天收盘，把金叉确认当天的涨幅也计入（numpy 切片比 pandas Series 快 ~12 倍）
        base = arr[gidx - 1] if gidx > 0 else arr[gidx]
        if base <= 0:
            continue
        seg = arr[gidx:end_idx + 1]
        peak_abs = gidx + int(seg.argmax())          # 周期内最高收盘日（市场对齐用）
        gain = seg.max() / base - 1
        if dates is not None:
            # 去市场步骤：绝对涨幅 → 超额涨幅（减去同期上证涨幅）
            gain = demarket.excess_gain(gain, dates, gidx, peak_abs)
        peak_gains.append(gain)
        # 量价效率：每换手一遍流通盘涨多少（% → 倍数）。换手缺失/过少的周期跳过。
        if turn is not None:
            t = turn[gidx:end_idx + 1]
            t = t[~np.isnan(t) & (t > 0.01)]
            if len(t) >= 3:
                cum_turn = float(t.sum()) / 100.0
                if cum_turn >= _EFF_MIN_TURNS:
                    effs.append((gain + 1.0) / cum_turn)

    if len(peak_gains) >= 5:
        # 均值易被极端暴涨拉偏（少数 +50% 周期抬高整体，如 000066 均值22.9% vs 中位1.8%），
        # 与中位数各取一半更公允
        robust_avg = 0.5 * statistics.mean(peak_gains) + 0.5 * statistics.median(peak_gains)
        wr = sum(1 for g in peak_gains if g > 0) / len(peak_gains)
        gain_score = _norm(robust_avg, 0.0, 0.24) * 100
        wr_score = _norm(wr, 0.5, 0.80) * 100
        base_score = round(0.6 * gain_score + 0.4 * wr_score, 1)

        # eff4 分：近 K 个周期均值（老周期会稀释当前资金行为，只看最近）。
        # 样本不足（<K 或无换手数据）时回退纯涨幅口径——与 demarket 失败回退同模式。
        if len(effs) >= _EFF_K:
            eff4 = statistics.mean(effs[-_EFF_K:])
            eff_score = min(_norm(eff4, 0.0, _EFF_NORM_HI) * 100, 100.0)
            return round((1 - _EFF_BLEND) * base_score + _EFF_BLEND * eff_score, 1)
        return base_score
    return 50.0  # 金叉样本不足，中性


def _golden_life_score(signals: list[tuple[int, str]]) -> float:
    """金叉寿命：出现金叉后能延续多久、是否反复横跳——"不反复"的度量。

    所有金叉→死叉周期都计入（**不剔除微横跳**：金叉后 1~4 天就死叉正是
    "反复横跳"的直接证据，应作为减分项而非剔除）：
    - 延续水平 = 平均寿命（截尾均值）+ 延续达标率（延续到 10/20 天占比）；
    - 反复惩罚 = 快速再次交叉率（相邻信号间隔 <5 天占比，金叉后快死叉 +
      死叉后快金叉双向都算）越高扣分越多；
    - 方差惩罚 = 寿命时好时坏不可信。

    注：不用"信号总次数"减分——MACD 标准参数下 DIF/DEA 天生灵敏，A 股
    几乎任何股票一年都有 30~40 次交叉，次数多是常态不是毛病；真正不可靠的
    是"交叉后快速再次交叉"（信号刚出就反转）。实验也表明该因子区分度有限
    （约 2~6 分），权重不宜超过涨幅。
    """
    if not signals:
        return 60.0
    lives: list[tuple[int, int]] = []  # (金叉idx, 寿命天数)
    for i in range(len(signals)):
        if signals[i][1] != "golden":
            continue
        # 相邻交叉必然异向：金叉的下一个信号必然是死叉
        if i + 1 < len(signals):
            nxt = signals[i + 1][0]
            lives.append((signals[i][0], nxt - signals[i][0]))
    if not lives:
        return 80.0  # 只有金叉无后续死叉：仍延续中，高分

    days = [t[1] for t in lives]

    # 快速再次交叉率：所有相邻信号（金叉↔死叉）间隔 <5 天 = 刚交叉完立刻反叉，
    # 双向统计（金叉后快死叉 + 死叉后快金叉），比只看金叉→死叉更全面
    intervals = [signals[i][0] - signals[i - 1][0] for i in range(1, len(signals))]
    quick_rate = sum(1 for d in intervals if d < 5) / len(intervals) if intervals else 0.0

    # 延续水平：截尾均值（去掉最长/最短各 10%）
    sorted_lives = sorted(lives, key=lambda t: t[1])
    trim = max(1, int(len(sorted_lives) * 0.1))
    kept = sorted_lives[trim:-trim] if len(sorted_lives) > 2 * trim else sorted_lives
    mean_life = statistics.mean([t[1] for t in kept])
    # 锚点 15 天：真实截尾平均寿命中位 11 天、最高约 16 天，15 贴近真实上沿
    life_part = _norm(mean_life, 3, 15) * 100

    # 延续达标率：延续到 10/20 天的金叉占比
    rate10 = sum(1 for d in days if d >= 10) / len(days)
    rate20 = sum(1 for d in days if d >= 20) / len(days)
    rate_part = (0.6 * rate10 + 0.4 * rate20) * 100

    # 不反复：快速再次交叉越少越好（反复横跳的直接证据，作为减分项）
    clean_part = (1 - quick_rate) * 100

    score = 0.35 * life_part + 0.35 * rate_part + 0.30 * clean_part

    # 方差惩罚：全部寿命（含微横跳）波动越大越不可信，按变异系数扣分
    if len(days) >= 3:
        mean0 = statistics.mean(days)
        if mean0 > 0:
            cv = statistics.stdev(days) / mean0
            score = max(0.0, score - _norm(cv, 0.8, 1.6) * 15)

    return round(score, 1)


def _cycle_stats(close: pd.Series, signals: list[tuple[int, str]]) -> tuple[list[float], list[float], list[int]]:
    """金叉/死叉周期统计：金叉峰值涨幅%、死叉谷值跌幅%、金叉寿命（天数）。

    供评分、决策树、详情展示共用——避免同一 df 上多处重复循环遍历 signals。
    numpy 数组切片（比 pandas Series 切片 + .max/.min 快 ~20 倍，扫描 1000+ 只时省数十秒）。
    """
    arr = close.to_numpy(dtype=float)
    n = len(arr)
    golden_peaks: list[float] = []
    death_valleys: list[float] = []
    lives: list[int] = []
    for i in range(len(signals)):
        s_idx, s_dir = signals[i]
        # 相邻交叉必然异向，signals[i+1] 即"下一个异向信号"（金叉后必是死叉，反之亦然）
        end_idx = signals[i + 1][0] if i + 1 < len(signals) else n - 1
        if end_idx <= s_idx or arr[s_idx] <= 0:
            continue
        seg = arr[s_idx:end_idx + 1]
        # 基准用信号日前一天收盘，把金叉/死叉确认当天的跳涨/跳跌也计入
        base = arr[s_idx - 1] if s_idx > 0 else arr[s_idx]
        if base <= 0:
            continue
        if s_dir == "golden":
            golden_peaks.append((seg.max() / base - 1) * 100)
        else:
            death_valleys.append((seg.min() / base - 1) * 100)
    for i in range(len(signals)):
        if signals[i][1] != "golden":
            continue
        if i + 1 < len(signals):
            lives.append(signals[i + 1][0] - signals[i][0])
    return golden_peaks, death_valleys, lives


def _peak_winrate(golden_peaks: list[float]) -> float | None:
    """金叉峰值胜率：冲过 +5% 的周期占比（供决策树可靠性补充）。"""
    if len(golden_peaks) >= 3:
        return sum(1 for g in golden_peaks if g > 5) / len(golden_peaks) * 100
    return None


def _signal_summary(close: pd.Series, signals: list[tuple[int, str]],
                    cycles: tuple[list[float], list[float], list[int]] | None = None) -> dict:
    """当前信号状态与历史金叉/死叉周期涨跌（详情页汇总展示用）。

    - current_signal / signal_days：最近一次是金叉还是死叉、已持续几个 bar
    - signal_gain_pct：当前信号期间累计涨跌幅 %
    - hist_golden_peak_pct / median / winrate：金叉周期峰值涨幅（均值/中位/胜率）
    - hist_death_trough_pct / median / winrate：死叉周期谷值跌幅（均值/中位/胜率）
    - hist_golden_days：金叉寿命天数（截尾均值 + 中位）
    cycles：预计算的周期统计（复用避免重复循环），None 时自行计算
    """
    info: dict = {}
    n = len(close)
    if signals:
        last_idx, last_dir = signals[-1]
        info["current_signal"] = last_dir  # golden / death
        info["signal_days"] = max(0, n - 1 - last_idx)
        if 0 <= last_idx < n and close.iloc[last_idx] > 0:
            # 基准用信号日前一天收盘，当前信号期间的涨幅也含确认当天的跳变
            base = close.iloc[last_idx - 1] if last_idx > 0 else close.iloc[last_idx]
            info["signal_gain_pct"] = round((close.iloc[-1] / base - 1) * 100, 2) if base > 0 else None
        else:
            info["signal_gain_pct"] = None

    # 历史金叉周期峰值涨幅、死叉周期谷值跌幅（周期统计复用，避免重复循环）
    if cycles is None:
        cycles = _cycle_stats(close, signals)
    golden_peaks, death_valleys, lives = cycles
    info["hist_golden_samples"] = len(golden_peaks)
    info["hist_golden_peak_pct"] = round(statistics.mean(golden_peaks), 2) if len(golden_peaks) >= 3 else None
    info["hist_golden_peak_median"] = round(statistics.median(golden_peaks), 2) if len(golden_peaks) >= 3 else None
    info["hist_golden_peak_winrate"] = (
        round(sum(1 for g in golden_peaks if g > 5) / len(golden_peaks) * 100, 1)
        if len(golden_peaks) >= 3 else None
    )
    info["hist_death_samples"] = len(death_valleys)
    info["hist_death_trough_pct"] = round(statistics.mean(death_valleys), 2) if len(death_valleys) >= 3 else None
    info["hist_death_trough_median"] = round(statistics.median(death_valleys), 2) if len(death_valleys) >= 3 else None
    info["hist_death_trough_winrate"] = (
        round(sum(1 for d in death_valleys if d < -5) / len(death_valleys) * 100, 1)
        if len(death_valleys) >= 3 else None
    )

    # 历史金叉平均持续天数（金叉→死叉间隔，截尾均值，与"不横跳分"同口径）
    if lives:
        sorted_lives = sorted(lives)
        trim = max(1, int(len(sorted_lives) * 0.1))
        kept = sorted_lives[trim:-trim] if len(sorted_lives) > 2 * trim else sorted_lives
        info["hist_golden_days"] = round(statistics.mean(kept), 1)
        info["hist_golden_days_median"] = round(statistics.median(kept), 1)
    else:
        info["hist_golden_days"] = None
        info["hist_golden_days_median"] = None
    return info


def _golden_continuation(df: pd.DataFrame, cache: dict | None = None) -> dict:
    """金叉延续性：出现金叉（MACD DIF 上穿 DEA）后能否成功上涨一大段、不反复横跳。

    纯历史统计评估（不看当前状态，而是历史数据对这只股票的总体评估）：
    = 0.60·金叉后大段上涨（涨幅分开方×10，放大低分区间的区分度）
      + 0.40·金叉寿命（有效延续达标 + 微横跳减分）
    ADX、DIF 斜率与当前金叉/死叉态（含斜率方向）仅作展示参考，不参与评分。
    cache：compute_indicator_cache 预计算指标（扫描复用），None 时自行计算
    """
    if cache:
        close = cache["close"]
        dif, dea, signals = cache["dif"], cache["dea"], cache["signals"]
        adx = cache["adx"]["adx"]
        dif_slope = cache["dif_slope"]
        current_golden = cache["golden"]
        peak_signal = cache["peak_signal"]
        peak_conf = cache["peak_conf"]
        vr20 = cache["vr20"]
        cycles = cache["cycles"]
    else:
        close = df["close"].astype(float)
        dif, dea, signals = macd_series(close)
        adx = compute_adx(df)["adx"]
        dif_slope = compute_dif_slope(dif)
        current_golden = is_golden(dif, dea)
        peak = _peak_features(close, dif, dea, df["volume"])
        peak_signal = peak["peak_signal"]
        peak_conf = peak["peak_conf"]
        vr20 = peak["vr20"]
        cycles = None

    # 去市场：传入 trade_date，让金叉延续分剥离上证普涨普跌（见 demarket 模块）
    dates = df["trade_date"].tolist() if "trade_date" in df.columns else None
    # 量价效率：传入换手率序列（daily 自带；weekly 由 to_bars 聚合出周换手）
    turnover = df["turnover"] if "turnover" in df.columns else None
    post_gain = _post_golden_gain(close, signals, dates=dates, turnover=turnover)
    life = _golden_life_score(signals)

    # 涨幅分 0-100 开方×10（√100×10=100 保持量纲）：压缩高分、放大低分区间的区分度。
    # 红利组金叉后涨幅普遍 <20，线性下低分区挤成一团；开方把 0-20 拉开到 0-45，区分度更好。
    post_eff = math.sqrt(max(post_gain, 0.0)) * 10

    # DIF 当前斜率：当日 DIF −（昨日 + 前日）/2（indicators/macd 统一实现，
    # 与趋势判断共用）。仅作展示参考，不参与评分。
    dif_slope_dir: str | None = None
    if dif_slope is not None:
        dif_slope_dir = "up" if dif_slope > 0 else ("down" if dif_slope < 0 else "flat")

    # 当前状态：DIF 在 DEA 上方 = 金叉态，下方 = 死叉态；再结合斜率描述强弱
    if dif_slope is None:
        current_state = "金叉" if current_golden else "死叉"
    elif current_golden:
        current_state = "金叉·走强" if dif_slope > 0 else "金叉·走弱"
    else:
        current_state = "死叉·修复" if dif_slope > 0 else "死叉·走弱"

    score = 0.40 * life + 0.60 * post_eff

    return {
        "score": round(score, 1),
        "post_golden_gain": round(post_gain, 1),
        "whipsaw_score": round(life, 1),
        "adx": adx,
        "signal_count": len(signals),
        "current_golden": current_golden,
        "current_state": current_state,
        "dif_slope": dif_slope,
        "dif_slope_dir": dif_slope_dir,
        "peak_signal": peak_signal,
        "peak_conf": peak_conf,
        "vr20": vr20,
        **_signal_summary(close, signals, cycles),
    }