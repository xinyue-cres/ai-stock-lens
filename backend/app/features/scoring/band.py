"""波段适配 + 股息安全垫：综合分的边缘维度（各占 0.20 / 0.10）。

- _band_score：幅度（sigma_20d 适中最佳）× 节奏（MA5 下方停留）
- _dividend_score：股息率归一化（ETF 给中性 50）
"""
from __future__ import annotations

import math
import statistics

import pandas as pd

from app.features.quant_factors import _sigma

from .base import _norm, _tri


def _band_score(df: pd.DataFrame, timeframe: str = "daily") -> dict:
    """波段适配 = 幅度 × 节奏（两个独立维度，实测 corr≈0）。

    - 幅度：sigma_20d 适中最佳（波动太小没肉、太大风险高）。真实分布
      P25=2.1% P50=3.3% P90=5.5%，锚点 2~7% 峰值 4%，P90 以上高波动才归零。
      注意锚点对应**日等效 sigma**：weekly/monthly 时把原始 sigma 按
      features.timeframe.SIGMA_SCALE 折回日尺度再喂锚，保证跨周期分布对齐。
    - 节奏：价格在 MA5 下方平均停留 bar 数（3~5.5 bar 线性，越长越从容）。
      太短=快探快弹赌博（来不及在均线下埋伏），适中偏长=有操作窗口。
      实测 daily p50=3.95 vs weekly p50=3.97（bar 单位），基本不变，无需折换。

    旧版 ATR/振幅 与 sigma 相关 0.93~0.97（本质同是波动），纯冗余；且锚点
    5% 太松造成 39~43% 满分白给分，故彻底去掉，只保留 sigma + 新增节奏。
    """
    from app.features.timeframe import SIGMA_SCALE

    close = df["close"].astype(float)
    # 打分只用 20 日波动率（sigma_20d），不再跑 compute_quant_features 全量 AI 因子——
    # 那些是 build_ai_input 的输入，扫描打分时算纯属浪费（占比 ~30%）
    sigma_raw = _sigma(close, 20)
    # 跨周期对齐：weekly sigma 天然是 daily 的 ~2.6 倍（实测），除以系数变回日等效
    sigma_scale = SIGMA_SCALE.get(timeframe, 1.0)  # type: ignore[arg-type]
    sigma_20 = sigma_raw / sigma_scale if sigma_raw is not None else None

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
        # sigma_raw 透出原始值供调试/对比（不折换）
        "sigma_20d_raw": round(sigma_raw * 100, 2) if sigma_raw is not None else None,
        "sigma_scale": sigma_scale,
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
