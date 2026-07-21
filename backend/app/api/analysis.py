from __future__ import annotations

import json
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.ai.analyzer import (
    analyze_anti_quant,
    analyze_debate,
    analyze_mean_reversion,
    analyze_reflexivity,
)
from app.ai.client import get_model_name
from app.db import get_session
from app.features.quant_factors import compute_quant_features
from app.models.ai_report import AIReport
from app.models.stock import Stock
from app.services import analysis_service, signals_service, sync_service
from app.services.analysis_service import load_kline_df
from app.services.stock_service import ensure_stock

router = APIRouter(prefix="/api/stocks/{code}", tags=["analysis"])


class AIReportOptions(BaseModel):
    horizon: str = "medium"  # short | medium
    force: bool = False


def _normalize_horizon(h: str | None) -> str:
    """当前保留 combined / anti_quant / reflexivity / mean_reversion 四个视角。
    历史请求中的 short/medium 一律归为 combined，避免破坏老 URL/客户端。"""
    if h == "anti_quant":
        return "anti_quant"
    if h == "reflexivity":
        return "reflexivity"
    if h == "mean_reversion":
        return "mean_reversion"
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
    previous = signals_service.get_previous_context(session, code, hz, model, exclude_as_of=as_of)
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
        df = load_kline_df(session, code)
        factors = compute_quant_features(df) if not df.empty else {"empty": True}
        result = analyze_anti_quant(stock_info, factors, indicators)
    elif hz == "reflexivity":
        result = analyze_reflexivity(stock_info, indicators)
    elif hz == "mean_reversion":
        from app.indicators.mean_reversion import compute_mean_reversion
        df = load_kline_df(session, code)
        mr_data = compute_mean_reversion(df) if not df.empty else {}
        result = analyze_mean_reversion(stock_info, mr_data, indicators)
    else:
        result = analyze_debate(stock_info, indicators)
    extras = {
        "key_signals": result.get("key_signals", []),
        "risks": result.get("risks", []),
        "scenarios": result.get("scenarios", []),
        "reflection": result.get("reflection"),
        "bull": result.get("bull"),
        "bear": result.get("bear"),
        "judge": result.get("judge"),
        "tradability": result.get("tradability"),
        "evidence_review": result.get("evidence_review"),
        "quant_output": result.get("quant_output"),
        "trap_risk": result.get("trap_risk"),
        "reflexivity_stage": result.get("reflexivity_stage"),
        "narrative": result.get("narrative"),
        "feedback_loop": result.get("feedback_loop"),
        "opportunity_level": result.get("opportunity_level"),
        "deviation_summary": result.get("deviation_summary"),
        "support_zones": result.get("support_zones"),
        "entry_plan": result.get("entry_plan"),
        "statistical_edge": result.get("statistical_edge"),
        "invalidation": result.get("invalidation"),
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
        created_at=datetime.now(),
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
    """一键生成 combined + anti_quant + reflexivity + mean_reversion 四个视角。任一失败不中断另一个。"""
    payload = payload or AIReportOptions()
    force = payload.force

    results: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for hz in ("combined", "anti_quant", "reflexivity", "mean_reversion"):
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
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "model": r.model,
        "key_signals": extras.get("key_signals", []),
        "risks": extras.get("risks", []),
        "scenarios": extras.get("scenarios", []),
        "reflection": extras.get("reflection"),
        "bull": extras.get("bull"),
        "bear": extras.get("bear"),
        "judge": extras.get("judge"),
        "tradability": extras.get("tradability"),
        "evidence_review": extras.get("evidence_review"),
        "quant_output": extras.get("quant_output"),
        "trap_risk": extras.get("trap_risk"),
        "reflexivity_stage": extras.get("reflexivity_stage"),
        "narrative": extras.get("narrative"),
        "feedback_loop": extras.get("feedback_loop"),
        "opportunity_level": extras.get("opportunity_level"),
        "deviation_summary": extras.get("deviation_summary"),
        "support_zones": extras.get("support_zones"),
        "entry_plan": extras.get("entry_plan"),
        "statistical_edge": extras.get("statistical_edge"),
        "invalidation": extras.get("invalidation"),
    }


def _parse_date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None
