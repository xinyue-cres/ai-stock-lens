"""Trader Agent 数据组装：把 4 份 AI 报告 + 当前指标 + 持仓压成一份输入包。

Trader 本身只做排序/去重/仓位化/个性化，不做新的分析 — 所以输入必须已经含有
scenarios 和 verdict；分析层保持不动。
"""
from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlmodel import Session, select

from app.ai.client import get_model_name
from app.indicators.engine import compute_all
from app.models.ai_report import AIReport
from app.models.kline import KlineDaily
from app.models.stock import Stock
from app.services import position_service, settings_service
from app.services.analysis_service import load_kline_df

logger = logging.getLogger(__name__)

_TRADER_HORIZONS = ["combined", "anti_quant", "reflexivity"]
_STALE_TRADING_DAYS = 2  # 报告 as_of 落后 K 线 as_of ≥ 2 交易日视为过期


_HORIZON_LABEL = {
    "combined": "综合",
    "anti_quant": "反量化",
    "reflexivity": "反身性",
}


def _latest_report(session: Session, code: str, model: str, horizon: str) -> AIReport | None:
    stmt = (
        select(AIReport)
        .where(AIReport.code == code, AIReport.model == model, AIReport.horizon == horizon)
        .order_by(AIReport.as_of_date.desc(), AIReport.created_at.desc())
        .limit(1)
    )
    return session.exec(stmt).first()


def _latest_kline_date(session: Session, code: str) -> date | None:
    row = session.exec(
        select(KlineDaily.trade_date)
        .where(KlineDaily.code == code)
        .order_by(KlineDaily.trade_date.desc())
        .limit(1)
    ).first()
    return row


def _trading_days_between(older: date, newer: date) -> int:
    """两个日期之间的交易日差（简易版：跳过周末，不考虑节假日）。older < newer → 正数。"""
    if older >= newer:
        return 0
    count = 0
    cur = older
    while cur < newer:
        cur = cur + timedelta(days=1)
        if cur.weekday() < 5:  # Mon-Fri
            count += 1
    return count


def _condense_report(report: AIReport) -> dict:
    """精简 AIReport → Trader 需要的字段：verdict / confidence / summary / scenarios。"""
    extras: dict = {}
    if report.extras_json:
        try:
            extras = json.loads(report.extras_json)
        except json.JSONDecodeError:
            extras = {}
    return {
        "as_of_date": str(report.as_of_date),
        "verdict": report.verdict,
        "confidence": report.confidence,
        "summary": report.summary,
        "scenarios": extras.get("scenarios", []),
        "key_signals": extras.get("key_signals", []),
        "risks": extras.get("risks", []),
    }


def build_action_plan_input(session: Session, code: str) -> dict[str, Any]:
    """组装 Trader Agent 的输入包。缺 AI 报告的 horizon 直接跳过（不阻塞），
    但会在 warnings 中显式标注，供 prompt 和前端使用。"""
    stock = session.get(Stock, code)
    if not stock:
        return {"empty": True, "reason": "unknown_stock"}
    model = get_model_name()

    # 1. 拉当前指标（K 线可能空 → 直接返回 empty）
    df = load_kline_df(session, code)
    if df.empty:
        return {"empty": True, "reason": "no_kline"}
    indicators = compute_all(df)
    latest_price = indicators.get("latest_price", {}) or {}
    close = latest_price.get("close")
    kline_as_of_str = indicators.get("as_of_date")
    kline_as_of = None
    if kline_as_of_str:
        try:
            kline_as_of = datetime.strptime(kline_as_of_str, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            kline_as_of = None

    # 2. 拉四份最近报告 + 判定过期
    reports: dict[str, dict] = {}
    warnings: list[str] = []
    for horizon in _TRADER_HORIZONS:
        r = _latest_report(session, code, model, horizon)
        label = _HORIZON_LABEL[horizon]
        if not r:
            warnings.append(f"{label}视角未生成")
            continue
        # 过期判定
        days_behind = 0
        if kline_as_of and r.as_of_date < kline_as_of:
            days_behind = _trading_days_between(r.as_of_date, kline_as_of)
        if days_behind >= _STALE_TRADING_DAYS:
            warnings.append(
                f"{label}报告基于 {r.as_of_date} 数据（落后 {days_behind} 交易日）"
            )
            # 过期报告仍纳入，但由 prompt 和前端提示用户
        reports[horizon] = {**_condense_report(r), "trading_days_behind": days_behind}

    # 3. 拉持仓
    pos = position_service.get_position(session, code)
    position_payload: dict | None = None
    if pos and pos.quantity > 0:
        pnl_pct = None
        if close and pos.cost_price > 0:
            pnl_pct = round((close - pos.cost_price) / pos.cost_price, 6)
        position_payload = {
            "quantity": pos.quantity,
            "cost_price": pos.cost_price,
            "opened_at": pos.opened_at.isoformat(),
            "note": pos.note,
            "unrealized_pnl_pct": pnl_pct,
            "market_value": close * pos.quantity if close else None,
        }

    return {
        "stock": {"code": code, "name": stock.name, "market": stock.market},
        "as_of": kline_as_of_str,
        "finalized": indicators.get("finalized"),
        "current": {
            "close": close,
            "pct_chg": latest_price.get("pct_chg"),
            "volume": latest_price.get("volume"),
            "turnover": latest_price.get("turnover"),
            "ma5": (indicators.get("ma") or {}).get("ma5"),
            "ma10": (indicators.get("ma") or {}).get("ma10"),
            "ma20": (indicators.get("ma") or {}).get("ma20"),
            "ma60": (indicators.get("ma") or {}).get("ma60"),
            "atr_stop_hint": (indicators.get("risk") or {}).get("stop_loss_hint"),
            "boll_upper": ((indicators.get("oscillators") or {}).get("boll") or {}).get("upper"),
            "boll_lower": ((indicators.get("oscillators") or {}).get("boll") or {}).get("lower"),
        },
        "reports": reports,
        "position": position_payload,
        "warnings": warnings,
        "total_capital": settings_service.get_total_capital(),
    }


def check_dependencies(session: Session, code: str) -> dict[str, Any]:
    """依赖状态快照：K 线 + 4 份报告 + 过期判定 + 持仓脉搏。供 GET /action-plan/deps 用。"""
    stock = session.get(Stock, code)
    if not stock:
        return {"empty": True, "reason": "unknown_stock"}
    model = get_model_name()

    # K 线状态
    kline_as_of = _latest_kline_date(session, code)
    df = load_kline_df(session, code)
    finalized: bool | None = None
    if not df.empty:
        indicators = compute_all(df)
        finalized = indicators.get("finalized")
    kline_status = {
        "as_of": kline_as_of.isoformat() if kline_as_of else None,
        "finalized": finalized,
        "empty": df.empty,
    }

    # 各 horizon 报告状态
    reports_status: dict[str, dict | None] = {}
    warnings: list[str] = []
    for horizon in _TRADER_HORIZONS:
        r = _latest_report(session, code, model, horizon)
        label = _HORIZON_LABEL[horizon]
        if not r:
            reports_status[horizon] = None
            warnings.append(f"{label}视角未生成")
            continue
        days_behind = 0
        if kline_as_of and r.as_of_date < kline_as_of:
            days_behind = _trading_days_between(r.as_of_date, kline_as_of)
        stale = days_behind >= _STALE_TRADING_DAYS
        if stale:
            warnings.append(f"{label}报告落后 {days_behind} 交易日")
        reports_status[horizon] = {
            "as_of": r.as_of_date.isoformat(),
            "verdict": r.verdict,
            "trading_days_behind": days_behind,
            "stale": stale,
            "created_at": r.created_at.isoformat() + "Z",
        }

    # 持仓脉搏：持仓 updated_at 晚于最新 action_plan created_at → dirty
    pos = position_service.get_position(session, code)
    latest_plan = _latest_report(session, code, model, "action_plan")
    position_dirty = False
    if pos and latest_plan and pos.updated_at > latest_plan.created_at:
        position_dirty = True
        warnings.append("持仓已变更，建议刷新操作指示")

    # ready = K 线存在 + 至少 1 份非过期报告
    has_fresh_report = any(
        r for r in reports_status.values() if r and not r["stale"]
    )
    ready = not kline_status["empty"] and has_fresh_report

    return {
        "kline": kline_status,
        "reports": reports_status,
        "position_dirty": position_dirty,
        "ready": ready,
        "warnings": warnings,
    }
