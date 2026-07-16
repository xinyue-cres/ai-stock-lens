from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.ai.analyzer import analyze_trader
from app.ai.client import get_model_name
from app.db import get_session
from app.models.ai_report import AIReport
from app.models.stock import Stock
from app.services import trader_service
from app.services.stock_service import ensure_stock

router = APIRouter(prefix="/api/stocks/{code}", tags=["action-plan"])


class ActionPlanOptions(BaseModel):
    force: bool = False


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _action_plan_to_dict(report: AIReport, cached: bool, stock: Stock | None) -> dict:
    """把 horizon='action_plan' 的 AIReport 拆成 Trader 前端结构。"""
    extras: dict = {}
    if report.extras_json:
        try:
            extras = json.loads(report.extras_json)
        except json.JSONDecodeError:
            extras = {}
    return {
        "cached": cached,
        "code": report.code,
        "name": stock.name if stock else None,
        "as_of_date": str(report.as_of_date),
        "model": report.model,
        "overall_stance": report.verdict,
        "summary": report.summary,
        "actions": extras.get("actions", []),
        "position_advice": extras.get("position_advice"),
        "conflicts": extras.get("conflicts", []),
        "bias_checks": extras.get("bias_checks", []),
        "confidence_adjustment": extras.get("confidence_adjustment", 0.0),
        "created_at": report.created_at.isoformat() + "Z",
    }


@router.get("/action-plan")
def get_action_plan(code: str, session: Session = Depends(get_session)):
    """只读最新 action_plan，不触发生成。"""
    stock = session.get(Stock, code)
    model = get_model_name()
    stmt = (
        select(AIReport)
        .where(AIReport.code == code, AIReport.model == model, AIReport.horizon == "action_plan")
        .order_by(AIReport.as_of_date.desc(), AIReport.created_at.desc())
        .limit(1)
    )
    cached = session.exec(stmt).first()
    if not cached:
        return {"cached": False, "empty": True}
    return _action_plan_to_dict(cached, cached=True, stock=stock)


@router.get("/action-plan/deps")
def get_action_plan_deps(code: str, session: Session = Depends(get_session)):
    """依赖状态：K 线 as_of + 4 份 AI 报告状态 + 过期判定 + warnings 列表。"""
    return trader_service.check_dependencies(session, code)


@router.post("/action-plan")
def gen_action_plan(
    code: str,
    payload: ActionPlanOptions | None = None,
    session: Session = Depends(get_session),
):
    payload = payload or ActionPlanOptions()
    stock = ensure_stock(session, code)
    model = get_model_name()

    input_bundle = trader_service.build_action_plan_input(session, code)
    if input_bundle.get("empty"):
        raise HTTPException(400, f"数据不足：{input_bundle.get('reason')}")
    if not input_bundle.get("reports"):
        raise HTTPException(400, "至少需要一份 AI 分析报告，请先生成任一 horizon")

    as_of = _parse_date(input_bundle.get("as_of")) or date.today()

    if not payload.force:
        stmt = (
            select(AIReport)
            .where(
                AIReport.code == code,
                AIReport.model == model,
                AIReport.horizon == "action_plan",
                AIReport.as_of_date == as_of,
            )
            .order_by(AIReport.created_at.desc())
            .limit(1)
        )
        cached = session.exec(stmt).first()
        if cached:
            return _action_plan_to_dict(cached, cached=True, stock=stock)

    result = analyze_trader(input_bundle)
    extras = {
        "actions": result.get("actions", []),
        "position_advice": result.get("position_advice"),
        "conflicts": result.get("conflicts", []),
        "bias_checks": result.get("bias_checks", []),
        "confidence_adjustment": result.get("confidence_adjustment", 0.0),
    }
    report = AIReport(
        code=code,
        as_of_date=as_of,
        model=model,
        horizon="action_plan",
        report_md="",
        verdict=result.get("overall_stance", "wait"),
        confidence=None,
        summary=result.get("summary", ""),
        extras_json=json.dumps(extras, ensure_ascii=False),
        created_at=datetime.now(),
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    return _action_plan_to_dict(report, cached=False, stock=stock)
