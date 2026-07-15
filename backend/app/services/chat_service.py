"""个股对话服务：组装上下文 + 流式调用 AI。"""
from __future__ import annotations

import json
import logging
from typing import Any, Generator

from sqlmodel import Session

from app.ai.client import get_ai_client, get_model_name
from app.ai.prompts import CHAT_SYSTEM
from app.services import trader_service

logger = logging.getLogger(__name__)

_MAX_HISTORY = 20  # 最多保留最近 20 轮对话


def build_chat_context(session: Session, code: str) -> str:
    """把个股全量分析上下文压成一段结构化文本，注入 system prompt。"""
    bundle = trader_service.build_action_plan_input(session, code)

    if bundle.get("empty"):
        return f"（股票 {code} 暂无可用数据：{bundle.get('reason')}）"

    stock = bundle["stock"]
    current = bundle.get("current") or {}
    position = bundle.get("position")
    reports = bundle.get("reports") or {}
    warnings = bundle.get("warnings") or []

    # 读操作指示
    from app.ai.client import get_model_name as _model
    from app.models.ai_report import AIReport
    from sqlmodel import select

    model = _model()
    action_plan_row = session.exec(
        select(AIReport)
        .where(AIReport.code == code, AIReport.model == model, AIReport.horizon == "action_plan")
        .order_by(AIReport.as_of_date.desc(), AIReport.created_at.desc())
        .limit(1)
    ).first()

    action_plan_block = ""
    if action_plan_row and action_plan_row.extras_json:
        try:
            ap = json.loads(action_plan_row.extras_json)
            stance = ap.get("overall_stance", "")
            summary = ap.get("summary", "")
            actions = ap.get("actions", [])
            actions_text = "\n".join(
                f"  [{a.get('priority')}] {a.get('type')} - {a.get('trigger_desc')} "
                f"(仓位:{a.get('size_hint')}, 止损:{a.get('stop_loss')}, 目标:{a.get('target_price')})"
                for a in actions
            )
            bias_checks = ap.get("bias_checks") or []
            bias_text = "\n".join(
                f"  🚫 {b.get('do_not') or b.get('trigger','')} → ✅ {b.get('do_instead') or b.get('counter_action','')}"
                for b in bias_checks
            )
            action_plan_block = f"""
== 操作指示 (Trader, as_of {action_plan_row.as_of_date}) ==
stance: {stance}
summary: {summary}
actions:
{actions_text}
散户偏差提醒:
{bias_text}
"""
        except (json.JSONDecodeError, TypeError):
            pass

    # 报告块
    reports_block = ""
    for horizon, r in reports.items():
        label = trader_service._HORIZON_LABEL.get(horizon, horizon)
        scenarios_text = ""
        for s in (r.get("scenarios") or [])[:4]:
            if isinstance(s, dict):
                scenarios_text += f"    [{s.get('direction','')}] {s.get('trigger','')} → {s.get('action','')}\n"
        reports_block += f"""
-- {label}分析 (as_of {r.get('as_of_date')}, verdict={r.get('verdict')}, conf={r.get('confidence')}) --
summary: {r.get('summary', '')}
信号: {', '.join(r.get('key_signals', [])[:4])}
风险: {', '.join(r.get('risks', [])[:4])}
预案:
{scenarios_text}"""

    # 持仓块
    pos_block = "当前未持仓"
    if position:
        pnl = position.get("unrealized_pnl_pct")
        pnl_str = f"{pnl*100:.2f}%" if pnl is not None else "N/A"
        pos_block = (
            f"{position['quantity']}股 · 成本{position['cost_price']} · "
            f"浮盈{pnl_str} · 市值{position.get('market_value')}"
        )

    # 组装
    context = f"""【股票】{stock['name']}（{stock['code']}）
【数据截止】{bundle.get('as_of')}

== 技术指标快照 ==
收盘: {current.get('close')} | 涨跌: {current.get('pct_chg')}%
MA5/10/20/60 = {current.get('ma5')} / {current.get('ma10')} / {current.get('ma20')} / {current.get('ma60')}
BOLL 上/下轨 = {current.get('boll_upper')} / {current.get('boll_lower')}
ATR止损参考 = {current.get('atr_stop_hint')}

== 持仓 ==
{pos_block}

{reports_block}
{action_plan_block}"""

    if warnings:
        context += f"\n⚠️ 注意: {'; '.join(warnings)}"

    return context


def stream_chat(
    session: Session, code: str, messages: list[dict[str, str]], *, inject_context: bool = True
) -> Generator[str, None, None]:
    """流式对话。inject_context=True 时注入全量个股上下文（首轮），否则只用轻量 system。"""
    if inject_context:
        context = build_chat_context(session, code)
        system = CHAT_SYSTEM.replace("{context}", context)
    else:
        system = CHAT_SYSTEM.replace(
            "{context}",
            f"（上下文已在首轮注入，当前股票代码：{code}，请基于对话历史继续回答）",
        )

    # 截断历史
    trimmed = messages[-_MAX_HISTORY * 2:] if len(messages) > _MAX_HISTORY * 2 else messages

    client = get_ai_client()
    model = get_model_name()

    full_messages = [{"role": "system", "content": system}] + trimmed

    try:
        stream = client.chat.completions.create(
            model=model,
            messages=full_messages,
            stream=True,
            temperature=0.5,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                yield f"data: {json.dumps({'content': delta.content}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        logger.exception("chat stream error")
        yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
