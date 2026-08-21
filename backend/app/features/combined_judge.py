"""日/周线合并评判：从 stock_score 的 daily + weekly 两条腿合成综合视图。

核心哲学（与用户共同确定）：
- 周线 = 方向层（该不该碰这只票）
- 日线 = 时机层（什么时候进）
- 两者地位不同 → 不能简单加权，要按状态矩阵合并

7 档 combined_stage 输出（合并后）：
- strong_buy            : 周强 + 日强（pullback/pullback）
- buy                   : 周强 + 日反弹（pullback/left_entry）
- watch_buy             : 周强 + 日整理（pullback/range / strong_up/pullback 已含）
- deep_pullback_entry   : 周强 + 日跌（pullback/downtrend）周线趋势内的深度回踩
- light_buy             : 周中 + 日强（range/pullback / left_entry/pullback / strong_up/left_entry）
- watch                 : 都中性 / 信息不足
- avoid                 : 任何一方明确"避"（weekly=downtrend / overheat，或 daily=overheat）
"""
from __future__ import annotations

from typing import TypedDict


# ---------------------------------------------------------------------------
# 状态矩阵
# ---------------------------------------------------------------------------

# (weekly_stage, daily_stage) → combined_stage
_MATRIX: dict[tuple[str, str], str] = {
    # weekly = pullback_entry（周趋势向上 + 回踩完成）
    ("pullback_entry", "pullback_entry"): "strong_buy",
    ("pullback_entry", "left_entry"): "buy",
    ("pullback_entry", "range"): "watch_buy",
    ("pullback_entry", "downtrend"): "deep_pullback_entry",
    ("pullback_entry", "strong_uptrend"): "buy",
    ("pullback_entry", "weak_golden"): "watch_buy",
    ("pullback_entry", "overheat"): "avoid",
    ("pullback_entry", "insufficient"): "watch_buy",
    # weekly = strong_uptrend（周趋势明确向上）
    ("strong_uptrend", "pullback_entry"): "strong_buy",
    ("strong_uptrend", "left_entry"): "light_buy",
    ("strong_uptrend", "range"): "light_buy",
    ("strong_uptrend", "downtrend"): "avoid",
    ("strong_uptrend", "strong_uptrend"): "strong_buy",
    ("strong_uptrend", "weak_golden"): "watch",
    ("strong_uptrend", "overheat"): "avoid",
    ("strong_uptrend", "insufficient"): "watch",
    # weekly = range（中性整理）
    ("range", "pullback_entry"): "light_buy",
    ("range", "left_entry"): "light_buy",
    ("range", "range"): "watch",
    ("range", "downtrend"): "avoid",
    ("range", "strong_uptrend"): "light_buy",
    ("range", "weak_golden"): "watch",
    ("range", "overheat"): "avoid",
    ("range", "insufficient"): "watch",
    # weekly = left_entry（周线级左侧机会，本身已激进）
    ("left_entry", "pullback_entry"): "light_buy",
    ("left_entry", "left_entry"): "watch",
    ("left_entry", "range"): "watch",
    ("left_entry", "downtrend"): "avoid",
    ("left_entry", "strong_uptrend"): "light_buy",
    ("left_entry", "weak_golden"): "avoid",
    ("left_entry", "overheat"): "avoid",
    ("left_entry", "insufficient"): "watch",
    # weekly = weak_golden（假金叉，不可靠）
    ("weak_golden", "pullback_entry"): "watch",
    ("weak_golden", "left_entry"): "avoid",
    ("weak_golden", "range"): "watch",
    ("weak_golden", "downtrend"): "avoid",
    ("weak_golden", "strong_uptrend"): "watch",
    ("weak_golden", "weak_golden"): "avoid",
    ("weak_golden", "overheat"): "avoid",
    ("weak_golden", "insufficient"): "watch",
    # weekly = downtrend（周下跌通道，任何 daily 信号都不接）
    ("downtrend", "*"): "avoid",
    # weekly = overheat（周已涨过头，回避）
    ("overheat", "*"): "avoid",
    # weekly = insufficient（数据不足，保守）
    ("insufficient", "pullback_entry"): "watch",
    ("insufficient", "left_entry"): "watch",
    ("insufficient", "range"): "watch",
    ("insufficient", "downtrend"): "avoid",
    ("insufficient", "strong_uptrend"): "watch",
    ("insufficient", "weak_golden"): "watch",
    ("insufficient", "overheat"): "watch",
    ("insufficient", "insufficient"): "watch",
}


# combined_stage → 描述 / 操作建议
_STAGE_META: dict[str, dict] = {
    "strong_buy": {
        "label": "强买信号",
        "color": "#dc2626",
        "icon": "🐂",
        "action": "重仓买入",
        "reason": "日周线同向看多（共振），双周期金叉回踩完成叠加，是最强入场信号",
        "trade_hint": "仓位可重（参考 30-50%）；止损跟踪 MA60；止盈看强趋势（参考 ADX 持续 ≥25）",
    },
    "buy": {
        "label": "买入",
        "color": "#ea580c",
        "icon": "📈",
        "action": "可买入",
        "reason": "周线看好 + 日线已反弹，配合度好",
        "trade_hint": "仓位中等（20-30%）；止损紧贴 MA20 下方",
    },
    "watch_buy": {
        "label": "观察买",
        "color": "#d97706",
        "icon": "👀",
        "action": "加自选盯日线",
        "reason": "周线看多但日线还在整理，等日线出明确信号（金叉/突破）再介入",
        "trade_hint": "暂不入场；把该票放进自选；每日看日线信号是否升级",
    },
    "deep_pullback_entry": {
        "label": "深度回踩",
        "color": "#65a30d",
        "icon": "🎯",
        "action": "轻仓分批",
        "reason": "周线趋势内日线超跌回踩，属回调入场机会；但需警惕基本面恶化",
        "trade_hint": "仓位轻（10-15%）+ 分批加仓；严格止损（如 -5%）",
    },
    "light_buy": {
        "label": "轻仓试",
        "color": "#0891b2",
        "icon": "💡",
        "action": "轻仓试仓",
        "reason": "周线中性/整理，但日线已有起涨信号",
        "trade_hint": "仓位轻（5-10%）+ 严止损（5%）；日线动能衰减立即出场",
    },
    "watch": {
        "label": "观望",
        "color": "#6b7280",
        "icon": "⏸️",
        "action": "不动",
        "reason": "日周线都无可观信号，等待",
        "trade_hint": "暂无操作；定期检查",
    },
    "avoid": {
        "label": "回避",
        "color": "#4b5563",
        "icon": "🚫",
        "action": "回避",
        "reason": "周线处于下跌通道 / 已涨幅透支 / 数据不足；任何日线反弹都不接",
        "trade_hint": "任何情况下都不介入；已持仓的尽快减仓",
    },
}


# combined_stage → combined_score 加成
_SCORE_BONUS: dict[str, float] = {
    "strong_buy": 8,
    "buy": 4,
    "deep_pullback_entry": 2,
    "light_buy": 2,
    "watch_buy": 0,
    "watch": 0,
    "avoid": -99,  # 强制沉底
}


# ---------------------------------------------------------------------------
# 公开 API
# ---------------------------------------------------------------------------


class _DailyWeekly(TypedDict, total=False):
    code: str
    name: str
    total_score: float
    signal_score: float
    trend_stage: str
    peak_signal: str | None
    peak_conf: int


def combined_stage(weekly_stage: str | None, daily_stage: str | None) -> str:
    """根据 (weekly_stage, daily_stage) 返回 7 档之一。

    未识别的 stage 视为 "watch"（保守），避免噪声 → 高分。
    None/insufficient → 都返回 watch。
    """
    w = weekly_stage or "insufficient"
    d = daily_stage or "insufficient"
    exact = _MATRIX.get((w, d))
    if exact:
        return exact
    # weekly wildcard (*)
    fallback = _MATRIX.get((w, "*"))
    if fallback:
        return fallback
    return "watch"


def combined_score(weekly_total: float, daily_total: float, stage: str) -> float:
    """综合分 = 0.6·weekly + 0.4·daily + stage 加成，clip 到 [0, 100]。

    周线占 60%（方向层权重高于时机层）。
    """
    base = 0.6 * weekly_total + 0.4 * daily_total
    bonus = _SCORE_BONUS.get(stage, 0)
    return max(0.0, min(100.0, round(base + bonus, 2)))


def combined_meta(stage: str) -> dict:
    """返回该 stage 的展示元数据（label/color/icon/action/reason/trade_hint）。"""
    return _STAGE_META.get(stage, _STAGE_META["watch"])


def combined_entry_reason(stage: str, weekly: dict, daily: dict) -> str:
    """生成操作建议主文（卡片"操作建议"段落首行）。

    weekly/daily dict 是 stock_score 行的核心字段合集：
    { total_score, signal_score, trend_stage, peak_signal, peak_conf }
    用于生成具体数字 + 具体阶段的组合描述。
    """
    meta = combined_meta(stage)
    base_reason = meta["reason"]

    # 把相应的"为什么"具体化：避免永远是同一句
    w_peak = weekly.get("peak_signal") or "无"
    d_peak = daily.get("peak_signal") or "无"
    details = []
    if stage == "strong_buy":
        details.append(f"周线 {weekly.get('trend_stage')} · 日线 {daily.get('trend_stage')}")
    elif stage == "deep_pullback_entry":
        details.append(f"日线已跌（{daily.get('trend_stage')}); 周线仍处 {weekly.get('trend_stage')} 上升趋势")
    elif stage == "buy":
        details.append(f"日线 peak={d_peak}")
    elif stage == "avoid":
        # 给出主要的"避"的原因
        if weekly.get("trend_stage") == "downtrend":
            details.append("周线下跌通道中")
        if weekly.get("trend_stage") == "overheat" or daily.get("trend_stage") == "overheat":
            details.append("高位/已涨幅透支")
        if weekly.get("trend_stage") == "insufficient" or daily.get("trend_stage") == "insufficient":
            details.append("数据不足")
    if daily.get("peak_signal") and daily.get("peak_conf", 0) >= 40:
        details.append(f"日线过峰信号 {daily['peak_signal']}(conf={daily['peak_conf']})")

    if details:
        return f"{base_reason}（{' · '.join(details)}）"
    return base_reason
