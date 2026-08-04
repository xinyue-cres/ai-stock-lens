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

import pandas as pd

from app.features.quant_factors import compute_quant_features
from app.indicators.adx import compute_adx
from app.indicators.risk import compute_risk

# 综合分权重
W_GOLDEN = 0.70
W_BAND = 0.20
W_DIVIDEND = 0.10

_MIN_ROWS = 60  # 少于 60 根日线不评分

_GOLDEN_HORIZONS = (5, 10, 20)  # 金叉后延续观察窗口


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

def _macd_cross_series(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    """日线 MACD DIF/DEA 金叉死叉信号（用户指定：金叉死叉判断改用 MACD）。

    DIF = EMA(fast) − EMA(slow)；DEA = EMA(DIF, signal)；
    金叉 = DIF 上穿 DEA；死叉 = DIF 下穿 DEA。
    返回 (dif, dea, [(idx,'golden'|'death'),...])。
    """
    dif = close.ewm(span=fast, adjust=False).mean() - close.ewm(span=slow, adjust=False).mean()
    dea = dif.ewm(span=signal, adjust=False).mean()
    signals: list[tuple[int, str]] = []
    for i in range(1, len(close)):
        d0, d1 = dif.iloc[i - 1], dif.iloc[i]
        e0, e1 = dea.iloc[i - 1], dea.iloc[i]
        if any(pd.isna(v) for v in (d0, d1, e0, e1)):
            continue
        if d0 <= e0 and d1 > e1:
            signals.append((i, "golden"))
        elif d0 >= e0 and d1 < e1:
            signals.append((i, "death"))
    return dif, dea, signals


def _post_golden_gain(close: pd.Series, signals: list[tuple[int, str]]) -> float:
    """历史金叉后大段上涨：后 20 日累计涨幅均值 + 胜率合成。

    优先用 20 日（"一大段"），样本 <5 逐级降级到 10/5 日；仍不足中性 50。
    """
    gains: dict[int, list[float]] = {h: [] for h in _GOLDEN_HORIZONS}
    for idx, direction in signals:
        if direction != "golden":
            continue
        for h in _GOLDEN_HORIZONS:
            end = idx + h
            if end < len(close) and close.iloc[idx] > 0:
                gains[h].append(close.iloc[end] / close.iloc[idx] - 1)

    for h in (20, 10, 5):
        arr = gains[h]
        if len(arr) >= 5:
            avg = statistics.mean(arr)
            wr = sum(1 for g in arr if g > 0) / len(arr)
            # 锚点 10%：A 股金叉后 20 日平均涨幅 2~5% 是常态，8~10% 已属很强，
            # 旧锚点 15% 让高分物理上不可达（实测分布验证），贴近真实上沿
            gain_score = _norm(avg, 0.0, 0.10) * 100
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
        for j in range(i + 1, len(signals)):
            if signals[j][1] == "death":
                lives.append((signals[i][0], signals[j][0] - signals[i][0]))
                break
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


def _golden_continuation(df: pd.DataFrame) -> dict:
    """金叉延续性：出现金叉（MACD DIF 上穿 DEA）后能否成功上涨一大段、不反复横跳。

    纯历史统计评估（用户确认：不看当前状态，而是历史数据对这只股票的总体评估）：
    = 0.60·金叉后大段上涨（涨幅分开方×10，放大低分区间的区分度）
      + 0.40·金叉寿命（有效延续达标 + 微横跳减分）
    ADX、DIF 斜率与当前金叉/死叉态（含斜率方向）仅作展示参考，不参与评分。
    """
    close = df["close"].astype(float)
    dif, dea, signals = _macd_cross_series(close)

    post_gain = _post_golden_gain(close, signals)
    life = _golden_life_score(signals)

    # 涨幅分 0-100 开方×10（√100×10=100 保持量纲）：压缩高分、放大低分区间的区分度。
    # 红利组金叉后涨幅普遍 <20，线性下低分区挤成一团；开方把 0-20 拉开到 0-45，区分度更好。
    post_eff = math.sqrt(max(post_gain, 0.0)) * 10

    adx = compute_adx(df)["adx"]

    # DIF 当前斜率：当日 DIF −（昨日 + 前日）/2（偏离近两日均值）。
    # 用户方案：比单日差分平滑（过滤"整体上升中的单日回调"噪声，方向不频繁翻转），
    # 又比 3/5 日窗口即时（参考窗口仅 2 天，宏桥 DIF 0.91→0.80 的回落能正确捕捉）。
    # 数据验证：与单日方向一致率 93%、与 3 日一致率 97%。仅作展示参考，不参与评分。
    dif_slope: float | None = None
    dif_slope_dir: str | None = None
    if len(dif) >= 3 and pd.notna(dif.iloc[-1]) and pd.notna(dif.iloc[-2]) and pd.notna(dif.iloc[-3]):
        dif_slope = round(float(dif.iloc[-1] - (dif.iloc[-2] + dif.iloc[-3]) / 2), 6)
        dif_slope_dir = "up" if dif_slope > 0 else ("down" if dif_slope < 0 else "flat")

    # 当前状态：DIF 在 DEA 上方 = 金叉态，下方 = 死叉态；再结合斜率描述强弱
    if len(dif) > 0 and pd.notna(dif.iloc[-1]) and pd.notna(dea.iloc[-1]):
        current_golden = bool(dif.iloc[-1] > dea.iloc[-1])
    else:
        current_golden = False
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
    qf = compute_quant_features(df)
    sigma_20 = qf.get("volatility", {}).get("sigma_20d")

    # 幅度分：20 日波动率适中最佳（三角归一）
    if sigma_20 is not None:
        amp = _tri(sigma_20, 0.02, 0.04, 0.07) * 100
    else:
        amp = 50.0

    # 节奏分：MA5 下方平均连续停留天数（值越小=反复跌破又弹回=赌博）
    close = df["close"].astype(float)
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
                is_fund: bool = False) -> dict | None:
    """对单只标的打分。df 需含 trade_date/open/high/low/close/volume/amount/turnover/pct_chg（升序）。

    返回完整打分 dict（含子维度明细 components）；数据不足返回 None。
    """
    if df is None or df.empty or len(df) < _MIN_ROWS:
        return None
    if "trade_date" in df.columns:
        df = df.sort_values("trade_date").reset_index(drop=True)

    golden = _golden_continuation(df)
    band = _band_score(df)
    dividend = _dividend_score(dividend_yield, is_fund)

    total = (W_GOLDEN * golden["score"]
             + W_BAND * band["score"]
             + W_DIVIDEND * dividend["score"])

    latest = df.iloc[-1]
    close = float(latest["close"])
    pct_chg = float(latest["pct_chg"]) if pd.notna(latest.get("pct_chg")) else None
    turnover = float(latest["turnover"]) if pd.notna(latest.get("turnover")) else None
    hist_vol = compute_risk(df).get("hist_vol_20d")

    return {
        "total_score": round(total, 2),
        "signal_score": round(golden["score"], 2),  # 复用字段名：金叉延续性分
        "lift_score": None,  # 趋势质量已并入金叉延续，不再单列
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
            },
            "band": band,
            "dividend": {"dividend_yield": dividend_yield},
        },
    }
