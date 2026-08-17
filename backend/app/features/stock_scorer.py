"""选股打分引擎：评估标的对"稳定上升趋势 + 中途波段"策略的适配度。

综合分 = 0.70·金叉延续性 + 0.20·波段适配 + 0.10·股息

核心维度是金叉延续性：出现金叉（日线 MACD 的 DIF 上穿 DEA）后能否成功上涨一大段、不反复横跳。
纯历史统计评估（不看当前状态，而是历史数据对这只股票的总体评估）：
0.60·金叉后大段上涨（涨幅分开方×10 放大低分区分度）+ 0.40·金叉寿命（有效延续+快速再次交叉减分）。
ADX、DIF 斜率与当前金叉/死叉态（含斜率方向）仅作展示参考，不参与评分。
波段适配衡量"仰卧起坐的肉"（波动空间），股息是安全垫。
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
from app.indicators.risk import compute_risk

# 综合分权重
W_GOLDEN = 0.70
W_BAND = 0.20
W_DIVIDEND = 0.10

_MIN_ROWS = 60  # 少于 60 根日线不评分

_GOLDEN_HORIZONS = (5, 10, 20)  # 金叉后延续观察窗口

# 动能加速度过峰阈值（A 方法）：acc_z = DIF 二阶导相对该股历史波动的 z-score。
# 方向由 acc_z 符号给出：acc_z < −_PEAK_Z = 动能急刹（顶部过峰）；acc_z > +_PEAK_Z = 动能急转（底部过峰）。
# 实时版验证：|acc_z|>1.0 报警率 ~19%（bar 旧判定 ~49%），|acc_z|>1.5 ~12.5%。取 1.0（预警宁可多报）。
_PEAK_Z = 1.0
_PEAK_CONF_STRONG = 51  # 过峰置信度"强"档（决策树降级门槛，误报 ~57%）；弱/极弱只前端提示


def _norm(x: float | None, lo: float, hi: float) -> float:
    """线性归一化到 [0,1]：x<=lo 得 0，x>=hi 得 1。"""
    if x is None:
        return 0.0
    return min(1.0, max(0.0, (x - lo) / (hi - lo)))


def _tri(x: float | None, lo: float, mid: float, hi: float) -> float:
    """三角归一化：峰值在中点 mid，落在 [lo,hi] 之外为 0（适中最佳）。"""
    if x is None:
        return 0.0
    if x <= lo or x >= hi:
        return 0.0
    if x <= mid:
        return (x - lo) / (mid - lo)
    return (hi - x) / (hi - mid)


# ---------------------------------------------------------------------------
# 金叉延续性（核心维度）
# ---------------------------------------------------------------------------

def _post_golden_gain(close: pd.Series, signals: list[tuple[int, str]]) -> float:
    """历史金叉后涨幅分：每次金叉→死叉周期内到峰值（区间最高收盘）的最大涨幅 + 胜率合成。

    用"周期内峰值涨幅"而非固定 20 日窗口——金叉长度不一（5~40 天），固定窗口
    测不准"这次金叉能涨到多高"；峰值涨幅衡量上涨潜力。
    锚点 24%（含金叉确认日跳涨后重新采样：周期级 p90 ≈24.5%、股票级 robust_avg p90 ≈12%）。
    """
    arr = close.to_numpy(dtype=float)
    n = len(arr)
    peak_gains: list[float] = []
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
        peak_gains.append(arr[gidx:end_idx + 1].max() / base - 1)

    if len(peak_gains) >= 5:
        # 均值易被极端暴涨拉偏（少数 +50% 周期抬高整体，如 000066 均值22.9% vs 中位1.8%），
        # 与中位数各取一半更公允
        robust_avg = 0.5 * statistics.mean(peak_gains) + 0.5 * statistics.median(peak_gains)
        wr = sum(1 for g in peak_gains if g > 0) / len(peak_gains)
        gain_score = _norm(robust_avg, 0.0, 0.24) * 100
        wr_score = _norm(wr, 0.5, 0.80) * 100
        return round(0.6 * gain_score + 0.4 * wr_score, 1)
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


def _peak_features(close: pd.Series, dif: pd.Series, dea: pd.Series,
                   volume: pd.Series) -> dict:
    """过峰信号特征（bar|acc_z + 置信度评级）：返回 dict。

    - 触发 = bar（柱缩/柱回升，方向相关）OR acc_z（动能急刹/急转）；
    - 置信度 = 触发类型(bar 15 / acc 25 / 双 45) + 量能(缩 0 / 中 15 / 放 30)；
      档位：极弱≤20 / 弱21-35 / 中36-50 / 强51-65 / 极强≥66（实测各档误报单调递减 88→45%）。
    - 方向由一阶导 slope 给出：动能向上看顶（柱缩/急刹），向下看底（柱回升/急转）。
      实测顶底对称；量能（vr20）作为"放量过峰更可信"的确认维度。
    """
    empty = {"acc_z": None, "slope_up": None, "peak_signal": None, "peak_conf": 0, "vr20": None}
    slope = dif - (dif.shift(1) + dif.shift(2)) / 2
    acc = slope.diff()
    fv = acc.dropna()
    if len(fv) < 30:
        return empty
    sd = float(fv.std(ddof=0))
    if sd <= 1e-9:
        return empty
    acc_z = float((acc.iloc[-1] - fv.mean()) / sd)
    slope_up = bool(slope.iloc[-1] > 0) if len(slope) > 0 else None
    if slope_up is None:
        return empty

    # 量比（周期相对量，消除个股差异）
    vr20: float | None = None
    if len(volume) >= 20:
        vol = volume.astype(float)
        m20 = vol.rolling(20).mean().iloc[-1]
        if pd.notna(m20) and m20 > 0:
            vr20 = float(vol.iloc[-1] / m20)

    # bar 触发（方向相关：动能向上柱缩=涨势衰减，向下柱回升=跌势衰竭）
    has_bar = False
    if len(dif) >= 3:
        bar = dif - dea
        prev = (bar.iloc[-2] + bar.iloc[-3]) / 2
        if slope_up:
            has_bar = bool(bar.iloc[-1] < prev)
        else:
            has_bar = bool(bar.iloc[-1] > prev)
    # acc 触发
    has_acc = (acc_z < -_PEAK_Z) if slope_up else (acc_z > +_PEAK_Z)

    if not (has_acc or has_bar):
        return {"acc_z": acc_z, "slope_up": slope_up,
                "peak_signal": "涨势延续" if slope_up else "跌势延续",
                "peak_conf": 0, "vr20": vr20}
    base = 45 if (has_acc and has_bar) else (25 if has_acc else 15)
    vol_add = 30 if (vr20 is not None and vr20 >= 1.3) else (15 if (vr20 is not None and vr20 >= 0.9) else 0)
    return {"acc_z": acc_z, "slope_up": slope_up,
            "peak_signal": "上涨过峰" if slope_up else "下跌过峰",
            "peak_conf": base + vol_add, "vr20": vr20}


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


def _signal_summary(close: pd.Series, signals: list[tuple[int, str]],
                    cycles: tuple[list[float], list[float], list[int]] | None = None) -> dict:
    """当前信号状态与历史金叉/死叉周期涨跌（详情页汇总展示用）。

    - current_signal / signal_days：最近一次是金叉还是死叉、已持续几个交易日
    - signal_gain_pct：当前信号期间累计涨跌幅 %
    - hist_golden_peak_pct / median / winrate：金叉周期峰值涨幅（均值/中位/胜率）
    - hist_death_trough_pct / median / winrate：死叉周期谷值跌幅（均值/中位/胜率）
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
    # 胜率（有效阈值）：金叉后冲过 +5% 才算有效——峰值几乎恒正，设阈值才有区分度
    info["hist_golden_peak_winrate"] = (
        round(sum(1 for g in golden_peaks if g > 5) / len(golden_peaks) * 100, 1)
        if len(golden_peaks) >= 3 else None
    )
    info["hist_death_samples"] = len(death_valleys)
    info["hist_death_trough_pct"] = round(statistics.mean(death_valleys), 2) if len(death_valleys) >= 3 else None
    info["hist_death_trough_median"] = round(statistics.median(death_valleys), 2) if len(death_valleys) >= 3 else None
    # 胜率（有效阈值）：死叉后跌破 -5% 才算有效
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

    纯历史统计评估（用户确认：不看当前状态，而是历史数据对这只股票的总体评估）：
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

    post_gain = _post_golden_gain(close, signals)
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

    # 过峰信号已由 _peak_features 统一计算（bar|acc_z 触发 + 置信度评级）：
    # 触发类型(bar/acc/双) × 量能(缩/中/放) → peak_conf 0-100，分 5 档（极弱/弱/中/强/极强）。
    # 强档以上(≥51)才够可信供决策树降级，弱/极弱只做前端提示。

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


# ---------------------------------------------------------------------------
# 波段适配 / 股息
# ---------------------------------------------------------------------------

def _band_score(df: pd.DataFrame) -> dict:
    """波段适配 = 幅度 × 节奏（两个独立维度，实测 corr≈0）。

    - 幅度：sigma_20d 适中最佳（波动太小没肉、太大风险高）。真实分布
      P25=2.1% P50=3.3% P90=5.5%，锚点 2~7% 峰值 4%，P90 以上高波动才归零。
    - 节奏：价格在 MA5 下方平均停留天数（3~5.5 天线性，越长越从容）。
      太短=快探快弹赌博（来不及在均线下埋伏），适中偏长=有操作窗口。

    旧版 ATR/振幅 与 sigma 相关 0.93~0.97（本质同是波动），纯冗余；且锚点
    5% 太松造成 39~43% 满分白给分，故彻底去掉，只保留 sigma + 新增节奏。
    """
    close = df["close"].astype(float)
    # 打分只用 20 日波动率（sigma_20d），不再跑 compute_quant_features 全量 AI 因子——
    # 那些是 build_ai_input 的输入，扫描打分时算纯属浪费（占比 ~30%）
    sigma_20 = _sigma(close, 20)

    # 幅度分：20 日波动率适中最佳（三角归一）
    if sigma_20 is not None:
        amp = _tri(sigma_20, 0.02, 0.04, 0.07) * 100
    else:
        amp = 50.0

    # 节奏分：MA5 下方平均连续停留天数（值越小=反复跌破又弹回=赌博）
    ma5 = close.rolling(5).mean()
    below = (close < ma5).fillna(False)
    runs: list[int] = []
    cur = 0
    for b in below.tolist():
        if b:
            cur += 1
        elif cur > 0:
            runs.append(cur)
            cur = 0
    if cur > 0:
        runs.append(cur)
    if runs:
        stay = statistics.mean(runs)
        rhythm = _norm(stay, 3.0, 5.5) * 100
    else:
        stay = None
        rhythm = 50.0

    score = 0.6 * amp + 0.4 * rhythm
    return {
        "score": round(score, 1),
        "sigma_20d": round(sigma_20 * 100, 2) if sigma_20 is not None else None,
        "ma5_stay_days": round(stay, 2) if stay is not None else None,
        "amplitude_score": round(amp, 1),
        "rhythm_score": round(rhythm, 1),
    }


def _dividend_score(dividend_yield: float | None, is_fund: bool) -> dict:
    """股息：个股用近 3 年平均股息率；ETF/LOF 无股息给中性 50。"""
    if is_fund or dividend_yield is None:
        return {"score": 50.0, "dividend_yield": dividend_yield}
    # 股息率 2%~6% 区间线性，越高越好
    return {
        "score": _norm(dividend_yield, 1.0, 6.0) * 100,
        "dividend_yield": dividend_yield,
    }


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------

def score_stock(df: pd.DataFrame, dividend_yield: float | None = None,
                is_fund: bool = False, cache: dict | None = None) -> dict | None:
    """对单只标的打分。df 需含 trade_date/open/high/low/close/volume/amount/turnover/pct_chg（升序）。

    返回完整打分 dict（含子维度明细 components）；数据不足返回 None。
    cache：compute_indicator_cache 预计算指标（扫描复用），None 时自行计算。
    """
    if df is None or df.empty or len(df) < _MIN_ROWS:
        return None
    if "trade_date" in df.columns:
        df = df.sort_values("trade_date").reset_index(drop=True)

    golden = _golden_continuation(df, cache=cache)
    band = _band_score(df)
    dividend = _dividend_score(dividend_yield, is_fund)

    total = (W_GOLDEN * golden["score"]
             + W_BAND * band["score"]
             + W_DIVIDEND * dividend["score"])

    latest = df.iloc[-1]
    close = float(latest["close"])
    pct_chg = float(latest["pct_chg"]) if pd.notna(latest.get("pct_chg")) else None
    turnover = float(latest["turnover"]) if pd.notna(latest.get("turnover")) else None
    # compute_indicator_cache 已算过 risk，直接用，避免重复计算（扫描 4000 只时省 2 倍）
    hist_vol = (cache["risk"]["hist_vol_20d"] if cache else compute_risk(df).get("hist_vol_20d"))

    return {
        "total_score": round(total, 2),
        "signal_score": round(golden["score"], 2),  # 复用字段名：金叉延续性分
        "band_score": round(band["score"], 2),
        "dividend_score": round(dividend["score"], 2),
        "close": round(close, 3),
        "pct_chg": pct_chg,
        "turnover": turnover,
        "hist_vol": hist_vol,
        "adx": golden["adx"],
        "dividend_yield": dividend_yield,
        "is_fund": is_fund,
        "components": {
            "signal": {
                "post_golden_gain": golden["post_golden_gain"],
                "whipsaw_score": golden["whipsaw_score"],
                "adx": golden["adx"],
                "signal_count": golden["signal_count"],
                "current_golden": golden["current_golden"],
                "current_state": golden["current_state"],
                "dif_slope": golden["dif_slope"],
                "dif_slope_dir": golden["dif_slope_dir"],
                "peak_signal": golden.get("peak_signal"),
                "peak_conf": golden.get("peak_conf"),
                "vr20": golden.get("vr20"),
                "current_signal": golden.get("current_signal"),
                "signal_days": golden.get("signal_days"),
                "signal_gain_pct": golden.get("signal_gain_pct"),
                "hist_golden_days": golden.get("hist_golden_days"),
                "hist_golden_days_median": golden.get("hist_golden_days_median"),
                "hist_golden_samples": golden.get("hist_golden_samples"),
                "hist_golden_peak_pct": golden.get("hist_golden_peak_pct"),
                "hist_golden_peak_median": golden.get("hist_golden_peak_median"),
                "hist_golden_peak_winrate": golden.get("hist_golden_peak_winrate"),
                "hist_death_samples": golden.get("hist_death_samples"),
                "hist_death_trough_pct": golden.get("hist_death_trough_pct"),
                "hist_death_trough_median": golden.get("hist_death_trough_median"),
                "hist_death_trough_winrate": golden.get("hist_death_trough_winrate"),
            },
            "band": band,
            "dividend": {"dividend_yield": dividend_yield},
        },
    }
