"""AI 输出规范化函数：清洗/校验模型返回的 JSON 字段。"""
from __future__ import annotations

from typing import Any


# -------------------- Scenarios / Conditions --------------------

_ALLOWED_KINDS = {"price", "volume_ratio"}
_ALLOWED_OPS = {">=", "<="}
_ALLOWED_TARGETS = {"close", "high", "low"}


def normalize_conditions(raw: Any) -> list[dict[str, Any]]:
    """校验并规范化 scenarios[*].conditions；无效项直接丢弃。"""
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for c in raw:
        if not isinstance(c, dict):
            continue
        kind = c.get("kind")
        op = c.get("op")
        val = c.get("value")
        if kind not in _ALLOWED_KINDS or op not in _ALLOWED_OPS:
            continue
        try:
            value = float(val)
        except (TypeError, ValueError):
            continue
        item: dict[str, Any] = {"kind": kind, "op": op, "value": value}
        if kind == "price":
            target = c.get("target") or "close"
            if target not in _ALLOWED_TARGETS:
                target = "close"
            item["target"] = target
        out.append(item)
    return out


def normalize_scenario(sc: dict[str, Any]) -> dict[str, Any]:
    """统一 scenario 字段：兼容旧字段名 + 归一 conditions。"""
    action = sc.get("action") or sc.get("target") or ""
    direction = sc.get("direction")
    if not direction:
        trigger = sc.get("trigger", "")
        name = sc.get("scenario", "")
        joined = f"{name} {trigger}"
        if any(kw in joined for kw in ["突破", "上涨", "站上", "金叉", "反弹"]):
            direction = "bullish"
        elif any(kw in joined for kw in ["跌破", "下跌", "回落", "死叉", "破位"]):
            direction = "bearish"
        else:
            direction = "neutral"
    scenario_type = sc.get("scenario_type") or "observe"
    valid_types = {"entry", "add", "trim", "stop_loss", "take_profit", "observe"}
    if scenario_type not in valid_types:
        scenario_type = "observe"
    return {
        "trigger": sc.get("trigger", ""),
        "action": action,
        "direction": direction,
        "scenario_type": scenario_type,
        "probability": sc.get("probability"),
        "risk_reward": sc.get("risk_reward") if isinstance(sc.get("risk_reward"), str) else None,
        "conditions": normalize_conditions(sc.get("conditions")),
    }


# -------------------- Actions (Trader) --------------------

_ACTION_TYPES = {
    "buy_dip", "add_position", "trim_position", "take_profit",
    "stop_loss", "wait_breakout", "wait_pullback", "observe",
}


def normalize_action(a: dict[str, Any]) -> dict[str, Any] | None:
    """规范化单条 action：trigger_conditions 走 normalize_conditions 修正结构。"""
    if not isinstance(a, dict):
        return None
    action_type = a.get("type")
    if action_type not in _ACTION_TYPES:
        action_type = "observe"
    priority_raw = a.get("priority")
    try:
        priority = int(priority_raw)
    except (TypeError, ValueError):
        priority = 3
    priority = max(1, min(5, priority))

    def _num_or_none(v: Any) -> float | None:
        try:
            f = float(v)
            if f != f:  # NaN
                return None
            return f
        except (TypeError, ValueError):
            return None

    return {
        "priority": priority,
        "type": action_type,
        "trigger_desc": a.get("trigger_desc") or "",
        "trigger_conditions": normalize_conditions(a.get("trigger_conditions")),
        "size_hint": a.get("size_hint") or "",
        "stop_loss": _num_or_none(a.get("stop_loss")),
        "target_price": _num_or_none(a.get("target_price")),
        "risk_reward": (a.get("risk_reward") or None) if isinstance(a.get("risk_reward"), str) else None,
        "distance_pct": _num_or_none(a.get("distance_pct")),
        "rationale": a.get("rationale") or "",
        "sourced_from": [
            h for h in (a.get("sourced_from") or [])
            if h in {"combined", "anti_quant", "reflexivity", "mean_reversion"}
        ],
    }


# -------------------- Bias Checks --------------------

_BIAS_TYPES = {
    "anchoring", "endowment", "disposition", "confirmation",
    "recency", "availability", "loss_aversion", "overconfidence",
    "herding", "sunk_cost",
}


def normalize_bias_check(b: Any) -> dict[str, Any] | None:
    if not isinstance(b, dict):
        return None
    bias = b.get("bias")
    if bias not in _BIAS_TYPES:
        return None
    return {
        "bias": bias,
        "label": (b.get("label") or "").strip(),
        "command": (b.get("command") or b.get("do_not") or b.get("trigger") or "").strip(),
        "invalidation": (b.get("invalidation") or "").strip(),
    }


# -------------------- Trap Risk (Anti-Quant) --------------------

_TRAP_TYPES = {"false_breakout", "crowded_chase", "stop_loss_cascade", "none"}
_TRAP_LEVELS = {"low", "medium", "high"}


def normalize_trap_risk(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {"type": "none", "level": "low", "evidence": []}
    trap_type = raw.get("type")
    if trap_type not in _TRAP_TYPES:
        trap_type = "none"
    level = raw.get("level")
    if level not in _TRAP_LEVELS:
        level = "low"
    evidence = [str(e) for e in (raw.get("evidence") or []) if e][:3]
    return {"type": trap_type, "level": level, "evidence": evidence}
