from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.ai.analyzer import (
    analyze_anti_quant,
    analyze_debate,
    analyze_reflexivity,
    analyze_trader,
)
from app.ai.client import get_model_name
from app.db import get_session
from app.features.quant_factors import compute_quant_features
from app.models.ai_report import AIReport
from app.models.stock import Stock
from app.services import analysis_service, sync_service, trader_service
from app.services.analysis_service import load_kline_df
from app.services.stock_service import ensure_stock

router = APIRouter(prefix="/api/stocks/{code}", tags=["analysis"])


class AIReportOptions(BaseModel):
    horizon: str = "medium"  # short | medium
    force: bool = False


def _normalize_horizon(h: str | None) -> str:
    """当前保留 combined / anti_quant / reflexivity 三个视角。
    历史请求中的 short/medium 一律归为 combined，避免破坏老 URL/客户端。"""
    if h == "anti_quant":
        return "anti_quant"
    if h == "reflexivity":
        return "reflexivity"
    return "combined"


@router.get("/kline")
def get_kline(code: str, session: Session = Depends(get_session)):
    result = analysis_service.analyze(session, code)
    if result.get("empty"):
        try:
            sync_service.sync_one_stock(session, code, full=True)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"数据同步失败：{e}") from e
        result = analysis_service.analyze(session, code)
    return result


@router.get("/ai-report")
def get_cached_report(
    code: str,
    horizon: str = "medium",
    session: Session = Depends(get_session),
):
    """只取缓存的 AI 报告，不触发生成。按 horizon 单独返回。"""
    stock = session.get(Stock, code)
    model = get_model_name()
    hz = _normalize_horizon(horizon)

    stmt = (
        select(AIReport)
        .where(AIReport.code == code, AIReport.model == model, AIReport.horizon == hz)
        .order_by(AIReport.as_of_date.desc(), AIReport.created_at.desc())
        .limit(1)
    )
    cached = session.exec(stmt).first()
    if not cached:
        return {"cached": False, "empty": True, "horizon": hz}
    return _report_to_dict(cached, cached=True, stock=stock)


@router.post("/ai-report")
def gen_ai_report(
    code: str,
    payload: AIReportOptions | None = None,
    session: Session = Depends(get_session),
):
    payload = payload or AIReportOptions()
    hz = _normalize_horizon(payload.horizon)
    stock = ensure_stock(session, code)

    ai_input = analysis_service.build_ai_input(session, code)
    if ai_input is None:
        raise HTTPException(status_code=404, detail="本地无 K 线数据，请先同步")
    stock_info, indicators = ai_input

    model = get_model_name()
    as_of = _parse_date(indicators.get("as_of_date")) or date.today()

    # 塞入上次报告 + 最新复盘作为反思上下文（排除今天的旧版本，避免自我反思）
    previous = analysis_service.get_previous_context(session, code, hz, model, exclude_as_of=as_of)
    if previous:
        indicators = {**indicators, "previous": previous}

    if not payload.force:
        stmt = (
            select(AIReport)
            .where(
                AIReport.code == code,
                AIReport.as_of_date == as_of,
                AIReport.model == model,
                AIReport.horizon == hz,
            )
            .order_by(AIReport.created_at.desc())
            .limit(1)
        )
        cached = session.exec(stmt).first()
        if cached:
            return _report_to_dict(cached, cached=True, stock=stock)
    # force=true：直接插新行，保留历史版本（同日多版本被允许）

    if hz == "anti_quant":
        # 反量化视角需要额外的量化因子快照，直接从库拉一次 df
        df = load_kline_df(session, code)
        factors = compute_quant_features(df) if not df.empty else {"empty": True}
        result = analyze_anti_quant(stock_info, factors, indicators)
    elif hz == "reflexivity":
        result = analyze_reflexivity(stock_info, indicators)
    else:
        # 目前对外只暴露 combined / anti_quant / reflexivity 三个视角；老的 short/medium
        # 请求会被 _normalize_horizon 归为 combined
        result = analyze_debate(stock_info, indicators)
    extras = {
        "key_signals": result.get("key_signals", []),
        "risks": result.get("risks", []),
        "scenarios": result.get("scenarios", []),
        "reflection": result.get("reflection"),
        # 辩论专属字段：bull / bear / judge 完整对象
        "bull": result.get("bull"),
        "bear": result.get("bear"),
        "judge": result.get("judge"),
        # 反量化专属：quant agent 的完整输出
        "quant_output": result.get("quant_output"),
        # 反身性专属
        "reflexivity_stage": result.get("reflexivity_stage"),
        "narrative": result.get("narrative"),
        "feedback_loop": result.get("feedback_loop"),
    }
    report = AIReport(
        code=code,
        as_of_date=as_of,
        model=model,
        horizon=hz,
        report_md=result.get("report_md", ""),
        verdict=result.get("verdict", "neutral"),
        confidence=result.get("confidence"),
        summary=result.get("summary"),
        extras_json=json.dumps(extras, ensure_ascii=False),
        created_at=datetime.utcnow(),
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    return _report_to_dict(report, cached=False, stock=stock)


@router.post("/ai-report/all")
def gen_all_ai_reports(
    code: str,
    payload: AIReportOptions | None = None,
    session: Session = Depends(get_session),
):
    """一键生成 combined + anti_quant + reflexivity 三个视角。任一失败不中断另一个。"""
    payload = payload or AIReportOptions()
    force = payload.force

    results: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for hz in ("combined", "anti_quant", "reflexivity"):
        try:
            results[hz] = gen_ai_report(
                code=code,
                payload=AIReportOptions(horizon=hz, force=force),
                session=session,
            )
        except HTTPException as e:
            errors[hz] = str(e.detail)
        except Exception as e:  # noqa: BLE001
            errors[hz] = f"{type(e).__name__}: {e}"

    return {
        "code": code,
        "generated": list(results.keys()),
        "failed": errors,
        "reports": results,
    }


def _report_to_dict(r: AIReport, cached: bool, stock=None) -> dict:
    extras: dict = {}
    if r.extras_json:
        try:
            extras = json.loads(r.extras_json)
        except json.JSONDecodeError:
            extras = {}
    return {
        "cached": cached,
        "code": r.code,
        "name": stock.name if stock else None,
        "horizon": r.horizon,
        "verdict": r.verdict,
        "confidence": r.confidence,
        "summary": r.summary,
        "report_md": r.report_md,
        "as_of_date": str(r.as_of_date),
        "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
        "model": r.model,
        "key_signals": extras.get("key_signals", []),
        "risks": extras.get("risks", []),
        "scenarios": extras.get("scenarios", []),
        "reflection": extras.get("reflection"),
        "bull": extras.get("bull"),
        "bear": extras.get("bear"),
        "judge": extras.get("judge"),
        "quant_output": extras.get("quant_output"),
        "reflexivity_stage": extras.get("reflexivity_stage"),
        "narrative": extras.get("narrative"),
        "feedback_loop": extras.get("feedback_loop"),
    }


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# -------------------- Trader Agent · 操作指示 --------------------

class ActionPlanOptions(BaseModel):
    force: bool = False


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
        "overall_stance": report.verdict,          # verdict 字段复用存 stance
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
    """依赖状态：K 线 as_of + 4 份 AI 报告状态 + 过期判定 + warnings 列表。

    前端 DependencyStatusBar 用这个渲染"数据 / AI 分析各视角"就绪程度。
    """
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
        report_md="",  # Trader 不产 markdown，前端渲染结构化 actions
        verdict=result.get("overall_stance", "wait"),
        confidence=None,
        summary=result.get("summary", ""),
        extras_json=json.dumps(extras, ensure_ascii=False),
        created_at=datetime.utcnow(),
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    return _action_plan_to_dict(report, cached=False, stock=stock)
