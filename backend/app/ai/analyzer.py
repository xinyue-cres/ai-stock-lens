"""AI 分析器：组装输入 → 调模型 → 解析结构化输出。"""
from __future__ import annotations

import json
import logging
from typing import Any

from app.ai.client import get_ai_client, get_model_name
from app.ai.normalizers import (
    normalize_action,
    normalize_bias_check,
    normalize_conditions,
    normalize_scenario,
    normalize_trap_risk,
)
from app.ai.prompts import (
    ANTI_QUANT_SYSTEM,
    BEAR_SYSTEM,
    BULL_SYSTEM,
    JUDGE_SYSTEM,
    QUANT_SIMULATOR_SYSTEM,
    REFLEXIVITY_SYSTEM,
    TRADER_SYSTEM,
    build_anti_quant_prompt,
    build_bear_prompt,
    build_bull_prompt,
    build_judge_prompt,
    build_quant_prompt,
    build_reflexivity_prompt,
    build_trader_prompt,
)

logger = logging.getLogger(__name__)


def _arg_text(a: Any) -> str:
    """兼容新旧格式的 argument 提取文本。"""
    if isinstance(a, str):
        return a
    if isinstance(a, dict):
        return a.get("claim") or str(a)
    return str(a)


def _chat_json(system: str, user: str, temperature: float = 0.3) -> dict[str, Any]:
    client = get_ai_client()
    model = get_model_name()
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        temperature=temperature,
    )
    raw = resp.choices[0].message.content or "{}"
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        logger.exception("AI 返回非合法 JSON: %s", raw[:200])
        return {}


def analyze_debate(stock_info: dict, indicators: dict) -> dict[str, Any]:
    """牛熊辩论：bull/bear 并行，judge 串行。"""
    from concurrent.futures import ThreadPoolExecutor

    logger.info("辩论开始 · 牛熊并行")
    with ThreadPoolExecutor(max_workers=2) as pool:
        bull_future = pool.submit(
            _chat_json, BULL_SYSTEM, build_bull_prompt(stock_info, indicators), 0.4
        )
        bear_future = pool.submit(
            _chat_json, BEAR_SYSTEM, build_bear_prompt(stock_info, indicators), 0.4
        )
        bull = bull_future.result()
        bear = bear_future.result()

    logger.info("辩论开始 · 裁判裁决")
    judge = _chat_json(
        JUDGE_SYSTEM,
        build_judge_prompt(stock_info, indicators, bull, bear),
        temperature=0.2,
    )

    # 兜底
    judge.setdefault("scenarios", [])
    judge.setdefault("risks", [])
    judge.setdefault("consensus", [])
    judge.setdefault("disputes", [])
    judge.setdefault("verdict", "neutral")
    judge.setdefault("summary", "")
    judge.setdefault("report_md", "")
    judge.setdefault("reflection", None)

    # scenarios 字段兼容：AI 可能返回 target/probability 而不是 action/direction
    normalized_scenarios = [
        normalize_scenario(sc) for sc in (judge.get("scenarios") or []) if isinstance(sc, dict)
    ]
    judge["scenarios"] = normalized_scenarios

    return {
        "bull": bull,
        "bear": bear,
        "judge": judge,
        "verdict": judge.get("verdict", "neutral"),
        "confidence": judge.get("confidence"),
        "tradability": judge.get("tradability"),
        "evidence_review": judge.get("evidence_review", []),
        "summary": judge.get("summary"),
        "report_md": judge.get("report_md", ""),
        "scenarios": normalized_scenarios,
        "risks": judge.get("risks", []),
        "reflection": judge.get("reflection"),
        "key_signals": [
            *[f"牛：{_arg_text(a)}" for a in bull.get("arguments", [])[:3]],
            *[f"熊：{_arg_text(a)}" for a in bear.get("arguments", [])[:3]],
        ],
    }


def analyze_anti_quant(
    stock_info: dict, factors: dict, indicators: dict,
) -> dict[str, Any]:
    """反量化视角：两次串行调用。

    Step 1: quant simulator 拿量化因子快照 + 大盘背景，产出机构动作画像
    Step 2: anti-quant 拿 quant 输出 + 日线/周线指标，产出散户可执行的反向预案
    """
    market = indicators.get("market") if isinstance(indicators, dict) else None

    logger.info("反量化 · Step 1 · 量化模拟")
    quant_output = _chat_json(
        QUANT_SIMULATOR_SYSTEM,
        build_quant_prompt(stock_info, factors, market or {}),
        temperature=0.3,
    )

    logger.info("反量化 · Step 2 · 反向策略")
    anti_output = _chat_json(
        ANTI_QUANT_SYSTEM,
        build_anti_quant_prompt(stock_info, quant_output, indicators),
        temperature=0.4,
    )

    # 兜底
    anti_output.setdefault("scenarios", [])
    anti_output.setdefault("risks", [])
    anti_output.setdefault("key_signals", [])
    anti_output.setdefault("verdict", "neutral")
    anti_output.setdefault("summary", "")
    anti_output.setdefault("report_md", "")
    anti_output.setdefault("reflection", None)

    scenarios = [
        normalize_scenario(sc) for sc in (anti_output.get("scenarios") or [])
        if isinstance(sc, dict)
    ]

    return {
        "verdict": anti_output.get("verdict", "neutral"),
        "confidence": anti_output.get("confidence"),
        "summary": anti_output.get("summary"),
        "report_md": anti_output.get("report_md", ""),
        "scenarios": scenarios,
        "risks": anti_output.get("risks", []),
        "key_signals": anti_output.get("key_signals", []),
        "reflection": anti_output.get("reflection"),
        # 反量化专属：量化 agent 的完整输出，前端展开可看
        "quant_output": quant_output,
        "trap_risk": normalize_trap_risk(anti_output.get("trap_risk")),
    }


def analyze_reflexivity(stock_info: dict, indicators: dict) -> dict[str, Any]:
    """反身性视角：单次调用，判定当前反馈循环阶段并给出预案。"""
    logger.info("反身性 · 单次调用")
    raw = _chat_json(
        REFLEXIVITY_SYSTEM,
        build_reflexivity_prompt(stock_info, indicators),
        temperature=0.4,
    )

    raw.setdefault("scenarios", [])
    raw.setdefault("risks", [])
    raw.setdefault("key_signals", [])
    raw.setdefault("verdict", "neutral")
    raw.setdefault("summary", "")
    raw.setdefault("report_md", "")
    raw.setdefault("reflection", None)
    raw.setdefault("reflexivity_stage", "range_bound")
    raw.setdefault("narrative", "")
    raw.setdefault("feedback_loop", {})

    scenarios = [
        normalize_scenario(sc) for sc in (raw.get("scenarios") or [])
        if isinstance(sc, dict)
    ]

    return {
        "verdict": raw.get("verdict", "neutral"),
        "confidence": raw.get("confidence"),
        "summary": raw.get("summary"),
        "report_md": raw.get("report_md", ""),
        "scenarios": scenarios,
        "risks": raw.get("risks", []),
        "key_signals": raw.get("key_signals", []),
        "reflection": raw.get("reflection"),
        # 反身性专属
        "reflexivity_stage": raw.get("reflexivity_stage"),
        "narrative": raw.get("narrative"),
        "feedback_loop": raw.get("feedback_loop"),
    }


def analyze_trader(payload: dict[str, Any]) -> dict[str, Any]:
    """Trader Agent：单次调用，把 4 份分析压成一份操作清单。"""
    logger.info("Trader · 组装 payload → 调用 AI")
    raw = _chat_json(
        TRADER_SYSTEM,
        build_trader_prompt(payload),
        temperature=0.25,
    )

    actions_raw = raw.get("actions") or []
    actions = [normalized for a in actions_raw
               if (normalized := normalize_action(a)) is not None]
    # 按优先级排序（1 最高，稳态排序保持 AI 内部倾向）
    actions.sort(key=lambda a: a["priority"])

    bias_checks_raw = raw.get("bias_checks") or []
    bias_checks = [b for b in
                   (normalize_bias_check(x) for x in bias_checks_raw)
                   if b is not None][:6]

    # confidence_adjustment: 多视角冲突时 AI 自行下调可信度
    conf_adj = raw.get("confidence_adjustment")
    try:
        conf_adj = max(-0.3, min(0.0, float(conf_adj))) if conf_adj is not None else 0.0
    except (TypeError, ValueError):
        conf_adj = 0.0

    return {
        "overall_stance": raw.get("overall_stance") or "wait",
        "summary": raw.get("summary") or "",
        "position_advice": raw.get("position_advice"),
        "actions": actions,
        "conflicts": [c for c in (raw.get("conflicts") or []) if isinstance(c, str)][:5],
        "bias_checks": bias_checks,
        "confidence_adjustment": conf_adj,
    }
