"""日/周线合并评判：从 stock_score 的 daily + weekly 两条腿合成综合视图。

核心哲学（与用户共同确定）：
- 周线 = 方向层（该不该碰这只票）
- 日线 = 时机层（什么时候进）
- 两者地位不同 → 不能简单加权，要按状态矩阵合并

12 档 combined_stage 输出（v1.4.0 对称化，见 docs/state-machine-redesign.md）：
- 买侧（5）：strong_buy / buy / watch_buy / deep_pullback_entry / light_buy
- 中央（1）：hold（可买可卖的混沌持有态，取代原 watch）
- 卖侧（5）：watch_sell / light_sell / deep_rally_exit / sell / strong_sell
- 系统外（1）：avoid（系统不评估：数据不足 / 双周假弱无信号）

对称轴 = 仓位操作视角中点；镜像对（strong/buy/watch/deep/light）加减分对称。
"""
from __future__ import annotations

from typing import TypedDict


# ---------------------------------------------------------------------------
# 状态矩阵
# ---------------------------------------------------------------------------

# (weekly_stage, daily_stage) → combined_stage
# 规则：weekly 为方向层，daily 为时机层；daily wildcard (w, "*") 兜底该周态下未列出的组合
_MATRIX: dict[tuple[str, str], str] = {
    # ── weekly = pullback_entry（周趋势向上，可入手）─────────────────────────
    ("pullback_entry", "pullback_entry"):  "strong_buy",
    ("pullback_entry", "strong_uptrend"):  "buy",
    ("pullback_entry", "left_entry"):      "buy",
    ("pullback_entry", "range"):           "watch_buy",
    ("pullback_entry", "weak_golden"):     "watch_buy",
    ("pullback_entry", "downtrend"):       "deep_pullback_entry",  # 周趋势内日超跌 → 假摔，接
    ("pullback_entry", "overheat"):        "watch_sell",           # 周买但日已过热 → 拉不动
    ("pullback_entry", "insufficient"):    "hold",

    # ── weekly = strong_uptrend（周强上升趋势）─────────────────────────────
    ("strong_uptrend", "pullback_entry"):  "strong_buy",
    ("strong_uptrend", "strong_uptrend"):  "strong_buy",
    ("strong_uptrend", "left_entry"):      "light_buy",
    ("strong_uptrend", "range"):           "light_buy",
    ("strong_uptrend", "weak_golden"):     "hold",
    ("strong_uptrend", "downtrend"):       "deep_rally_exit",      # 周强 + 日走差 → 反弹逢高减
    ("strong_uptrend", "overheat"):        "sell",
    ("strong_uptrend", "insufficient"):    "hold",

    # ── weekly = range（周中性整理，可交易但无方向）────────────────────────
    ("range", "pullback_entry"):           "light_buy",
    ("range", "strong_uptrend"):           "light_buy",
    ("range", "left_entry"):               "light_buy",
    ("range", "range"):                    "hold",
    ("range", "weak_golden"):              "hold",
    ("range", "downtrend"):                "watch_sell",           # 周平 + 日入下跌 → 盯减
    ("range", "overheat"):                 "light_sell",
    ("range", "insufficient"):             "hold",

    # ── weekly = left_entry（周左侧机会，本身激进）─────────────────────────
    ("left_entry", "pullback_entry"):      "light_buy",
    ("left_entry", "strong_uptrend"):      "light_buy",
    ("left_entry", "left_entry"):          "hold",                 # 双侧都左侧 → 不动等金叉
    ("left_entry", "range"):               "hold",
    ("left_entry", "weak_golden"):         "watch_sell",           # 周左侧 + 日走弱 → 不恋战
    ("left_entry", "downtrend"):           "watch_sell",
    ("left_entry", "overheat"):            "deep_rally_exit",      # 周左 + 日过热 → 反弹就跑
    ("left_entry", "insufficient"):        "hold",

    # ── weekly = weak_golden（周假金叉不可靠，不推荐买入）──────────────────
    # 对持仓者借反弹减仓；双周都假弱 → 无法评估 → avoid
    ("weak_golden", "pullback_entry"):     "watch_sell",
    ("weak_golden", "strong_uptrend"):     "watch_sell",
    ("weak_golden", "left_entry"):         "deep_rally_exit",
    ("weak_golden", "range"):              "avoid",                # 周假弱 + 日无方向 → 不评估
    ("weak_golden", "weak_golden"):        "avoid",                # 双周假弱 → 不评估
    ("weak_golden", "downtrend"):          "avoid",                # 周假弱 + 日弱 → 不评估
    ("weak_golden", "overheat"):           "strong_sell",          # 假金叉 + 日过热 → 清
    ("weak_golden", "insufficient"):       "hold",

    # ── weekly = downtrend（周下跌，持仓者该走 / 未持仓者禁区）─────────────
    ("downtrend", "downtrend"):            "strong_sell",          # 双周共振死叉 → 清仓
    ("downtrend", "overheat"):             "sell",
    ("downtrend", "weak_golden"):          "sell",
    ("downtrend", "range"):                "sell",
    ("downtrend", "strong_uptrend"):       "deep_rally_exit",      # 日强反弹 = 出逃窗口
    ("downtrend", "pullback_entry"):       "watch_sell",
    ("downtrend", "left_entry"):           "watch_sell",
    ("downtrend", "insufficient"):         "avoid",                # 周弱 + 数据不足 → 不评估

    # ── weekly = overheat（周已涨过头，持仓者该走 / 未持仓者禁区）──────────
    ("overheat", "overheat"):              "strong_sell",          # 双周过热 → 清仓
    ("overheat", "downtrend"):             "strong_sell",
    ("overheat", "strong_uptrend"):        "sell",
    ("overheat", "weak_golden"):           "sell",
    ("overheat", "range"):                 "watch_sell",
    ("overheat", "pullback_entry"):        "watch_sell",           # 周过热 + 日回踩 → 防钓底
    ("overheat", "left_entry"):            "deep_rally_exit",
    ("overheat", "insufficient"):          "avoid",                # 周过热 + 数据不足 → 不评估

    # ── weekly = insufficient（数据不足，保守中立）─────────────────────────
    ("insufficient", "*"):                 "hold",
}


# combined_stage → 描述 / 操作建议
_STAGE_META: dict[str, dict] = {
    "strong_buy": {
        "label": "强买信号",
        "color": "#dc2626",
        "action": "重仓买入",
        "reason": "日周线同向看多（共振），双周期金叉回踩完成叠加，是最强入场信号",
        "trade_hint": "仓位可重（参考 30-50%）；止损跟踪 MA60；止盈看强趋势（参考 ADX 持续 ≥25）",
    },
    "buy": {
        "label": "买入",
        "color": "#ea580c",
        "action": "可买入",
        "reason": "周线看好 + 日线已反弹，配合度好",
        "trade_hint": "仓位中等（20-30%）；止损紧贴 MA20 下方",
    },
    "deep_pullback_entry": {
        "label": "深度回踩",
        "color": "#65a30d",
        "action": "轻仓分批",
        "reason": "周线趋势内日线超跌回踩，属回调入场机会；但需警惕基本面恶化",
        "trade_hint": "仓位轻（10-15%）+ 分批加仓；严格止损（如 -5%）",
    },
    "watch_buy": {
        "label": "观察买",
        "color": "#d97706",
        "action": "先盯",
        "reason": "周线看多但日线还在整理，等日线出明确信号（金叉/突破）再介入",
        "trade_hint": "暂不入场；把该票放进自选；每日看日线信号是否升级",
    },
    "light_buy": {
        "label": "轻仓试",
        "color": "#0891b2",
        "action": "轻仓",
        "reason": "周线中性/整理，但日线已有起涨信号",
        "trade_hint": "仓位轻（5-10%）+ 严止损（5%）；日线动能衰减立即出场",
    },
    "hold": {
        "label": "持有",
        "color": "#6b7280",
        "action": "不动",
        "reason": "日周线都可交易但无明确方向，已持仓不乱动；未持仓不入；等信号升级",
        "trade_hint": "每日复查两条腿的日变化，往买/卖侧偏移再动",
    },
    "watch_sell": {
        "label": "观察卖",
        "color": "#d97706",
        "action": "先盯",
        "reason": "周线定调偏坏，日线出弱信号但未确认走坏，先盯减仓点",
        "trade_hint": "暂不减仓；等日线死叉 / 顶部过峰明确 → 升级到 sell / strong_sell",
    },
    "light_sell": {
        "label": "轻仓减",
        "color": "#0891b2",
        "action": "减仓",
        "reason": "周线走弱 + 日线还没确认走坏，先减仓戒风险",
        "trade_hint": "整体仓位降 25%，剩余待 daily 死叉确认加剧减",
    },
    "deep_rally_exit": {
        "label": "反弹离场",
        "color": "#65a30d",
        "action": "分批减仓",
        "reason": "周线已走坏，日线这一波反弹是离场窗口（不要当反转接回）",
        "trade_hint": "反弹接近 20/MA60 时重仓出清；反弹后日线再次走弱即按 strong_sell 清",
    },
    "sell": {
        "label": "卖出",
        "color": "#ea580c",
        "action": "中大仓减",
        "reason": "日/周线均已走坏，无深反机会，尽快出清",
        "trade_hint": "减仓 70%；剩余随第二日继续走差就出清",
    },
    "strong_sell": {
        "label": "强卖信号",
        "color": "#dc2626",
        "action": "清仓",
        "reason": "日周线同向走坏（双周共振死叉/双周过热），是最强离场信号",
        "trade_hint": "毕其功于一役：当日清 80%，次日全部离",
    },
    "avoid": {
        "label": "场外回避",
        "color": "#4b5563",
        "action": "不介入",
        "reason": "系统不评估：数据不足 / 双周假弱无信号；任何日线反弹不接，不要在此开仓",
        "trade_hint": "未持仓：坚决不介入；已持仓：先反弹减再进入 sell 流程",
    },
}


# combined_stage → combined_score 加成（镜像对对称：±8 / ±4 / ±2 / ±1，hold=0，avoid 沉底）
_SCORE_BONUS: dict[str, float] = {
    "strong_buy": 8,
    "buy": 4,
    "deep_pullback_entry": 2,
    "light_buy": 2,
    "watch_buy": 1,
    "hold": 0,
    "watch_sell": -1,
    "light_sell": -2,
    "deep_rally_exit": -2,
    "sell": -4,
    "strong_sell": -8,
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
    """根据 (weekly_stage, daily_stage) 返回 12 档之一。

    未识别的 stage 视为 "hold"（保守，可交易但不行动），避免噪声 → 高分。
    None/insufficient → 都返回 hold。
    """
    w = weekly_stage or "insufficient"
    d = daily_stage or "insufficient"
    exact = _MATRIX.get((w, d))
    if exact:
        return exact
    # daily wildcard (*)
    fallback = _MATRIX.get((w, "*"))
    if fallback:
        return fallback
    return "hold"


def combined_score(weekly_total: float, daily_total: float, stage: str) -> float:
    """综合分 = 0.6·weekly + 0.4·daily + stage 加成，clip 到 [0, 100]。

    周线占 60%（方向层权重高于时机层）。卖侧负加成保留 base 梯度（不再被 -99 一刀切 0），
    只有 avoid（系统不评估）才沉底。
    """
    base = 0.6 * weekly_total + 0.4 * daily_total
    bonus = _SCORE_BONUS.get(stage, 0)
    return max(0.0, min(100.0, round(base + bonus, 2)))


def combined_meta(stage: str) -> dict:
    """返回该 stage 的展示元数据（label/color/action/reason/trade_hint）。"""
    return _STAGE_META.get(stage, _STAGE_META["hold"])


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
    elif stage == "deep_rally_exit":
        # 卖侧的镜像归因：周线方向已坏，日线只是反弹窗口
        details.append(f"周线 {weekly.get('trend_stage')} · 日线 {daily.get('trend_stage')} 反弹")
    elif stage in ("sell", "strong_sell", "watch_sell", "light_sell"):
        reasons = []
        if weekly.get("trend_stage") in ("downtrend", "overheat", "weak_golden"):
            reasons.append(f"周线 {weekly.get('trend_stage')}")
        if daily.get("trend_stage") in ("downtrend", "overheat", "weak_golden"):
            reasons.append(f"日线 {daily.get('trend_stage')}")
        if reasons:
            details.append("·".join(reasons))
    elif stage == "avoid":
        # 给出主要的"不评估"的原因
        if weekly.get("trend_stage") == "insufficient" or daily.get("trend_stage") == "insufficient":
            details.append("数据不足")
        elif weekly.get("trend_stage") in ("weak_golden", "range") or daily.get("trend_stage") in ("weak_golden", "range"):
            details.append("双周假弱无信号")
        elif weekly.get("trend_stage") in ("downtrend", "overheat"):
            details.append(f"周线 {weekly.get('trend_stage')}")
    if daily.get("peak_signal") and daily.get("peak_conf", 0) >= 40:
        details.append(f"日线过峰信号 {daily['peak_signal']}(conf={daily['peak_conf']})")

    if details:
        return f"{base_reason}（{' · '.join(details)}）"
    return base_reason
