"""过峰信号特征：bar|acc_z 触发 + 置信度评级。

过峰 = 动能急刹/急转后趋势转向的早期预警。触发后按"位置 × 方向"四象限贴标签：
水下衰竭（下跌过峰/底部反转）偏多预警（左侧机会），水上衰竭（上涨过峰/顶部回落）偏空预警（拦追入）。
置信度 = 触发类型(bar 15 / acc 25 / 双 45) + 量能(缩 0 / 中 15 / 放 30)。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from app.indicators.macd import dif_slope_series

from .rates import _PEAK_Z


def _peak_features(close: pd.Series, dif: pd.Series, dea: pd.Series,
                   volume: pd.Series) -> dict:
    """过峰信号特征：返回 dict。

    - 触发 = bar（柱缩/柱回升，方向相关）OR acc_z（动能急刹/急转）；
    - 置信度 = base(bar/acc/双) + 量能加成，0-100 分 5 档；
    - 方向由 slope（DIF 一阶导）给出：动能向上看顶，向下看底。

    返回键：acc_z, slope_up, peak_signal, peak_conf, vr20。
    peak_signal 四象限：上涨过峰/顶部回落（水上）/下跌过峰/底部反转（水下），
    或（无触发时）涨势延续/跌势延续。
    """
    empty = {"acc_z": None, "slope_up": None, "peak_signal": None, "peak_conf": 0, "vr20": None}
    slope = dif_slope_series(dif)
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

    # 标签：四象限（dif 位置 × slope 方向），对称轴是"位置"——
    # 水下衰竭（下跌过峰/底部反转）= 左侧机会语义；水上衰竭（上涨过峰/顶部回落）= 风险预警语义。
    # 镜像配对：上涨过峰 ↔ 下跌过峰（顺区域方向的动能峰值），
    #           底部反转 ↔ 顶部回落（逆区域方向的首波减速）。
    # 消费端（trend_judge 的 peak_top/peak_bot、list.py 的 exclude_up）
    # 一直按这套语义写枚举，此处恢复产出后即刻对齐。
    dif_last = float(dif.iloc[-1])
    if slope_up:
        # DIF 从负区抬头（金叉前兆）单独叫"底部反转"，比"上涨过峰"更贴近发散
        label = "底部反转" if dif_last < 0 else "上涨过峰"
    else:
        # DIF 从正区低头（死叉前兆/回落中）叫"顶部回落"，与底部反转镜像
        label = "顶部回落" if dif_last > 0 else "下跌过峰"
    return {"acc_z": acc_z, "slope_up": slope_up,
            "peak_signal": label, "peak_conf": peak_conf, "vr20": vr20}
