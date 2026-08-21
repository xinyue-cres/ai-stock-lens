"""过峰信号特征：bar|acc_z 触发 + 置信度评级。

过峰 = 动能急刹/急转后趋势转向的早期预警。触发后按"位置 + 方向"四象限贴标签。
置信度 = 触发类型(bar 15 / acc 25 / 双 45) + 量能(缩 0 / 中 15 / 放 30)。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .rates import _PEAK_Z


def _peak_features(close: pd.Series, dif: pd.Series, dea: pd.Series,
                   volume: pd.Series) -> dict:
    """过峰信号特征：返回 dict。

    - 触发 = bar（柱缩/柱回升，方向相关）OR acc_z（动能急刹/急转）；
    - 置信度 = base(bar/acc/双) + 量能加成，0-100 分 5 档；
    - 方向由 slope（DIF 一阶导）给出：动能向上看顶，向下看底。

    返回键：acc_z, slope_up, peak_signal, peak_conf, vr20。
    peak_signal 四象限：上涨过峰/下跌过峰/底部反转/顶部回落（dif 位置 × slope_up），
    或（无触发时）涨势延续/跌势延续。
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
    peak_conf = base + vol_add

    # 四象限标签：slope_up × dif 位置（dif 是 DIF 当前值，反映 MACD 负/正区）
    # acc_z 只看方向不看位置：dif<0 底部抬头被借误为顶部 → 改成"底部翻转"
    dif_last = float(dif.iloc[-1])
    if slope_up and dif_last < 0:
        return {"acc_z": acc_z, "slope_up": slope_up,
                "peak_signal": "底部反转", "peak_conf": peak_conf, "vr20": vr20}
    if not slope_up and dif_last > 0:
        return {"acc_z": acc_z, "slope_up": slope_up,
                "peak_signal": "顶部回落", "peak_conf": peak_conf, "vr20": vr20}

    return {"acc_z": acc_z, "slope_up": slope_up,
            "peak_signal": "上涨过峰" if slope_up else "下跌过峰",
            "peak_conf": peak_conf, "vr20": vr20}
