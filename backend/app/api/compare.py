"""多股横向对比 AI 分析 API。"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.ai.analyzer import analyze_compare
from app.ai.client import get_model_name
from app.db import get_session
from app.indicators.engine import compute_all
from app.models.ai_report import AIReport
from app.models.stock import Stock
from app.services.analysis_service import load_kline_df

router = APIRouter(prefix="/api/compare", tags=["compare"])


class CompareRequest(BaseModel):
    codes: list[str]
    force: bool = False


def _build_stock_snapshot(session: Session, code: str, model: str) -> dict | None:
    """为单只票构建对比分析所需的快照数据。"""
    stock = session.get(Stock, code)
    if not stock:
        return None

    df = load_kline_df(session, code)
    if df.empty:
        return {"code": code, "name": stock.name or code, "empty": True}

    indicators = compute_all(df)
    latest = indicators.get("latest_price", {}) or {}
    ma = indicators.get("ma", {}) or {}
    boll = indicators.get("boll", {}) or {}

    # 取最新 combined 报告摘要
    report = session.exec(
        select(AIReport)
        .where(AIReport.code == code, AIReport.model == model, AIReport.horizon == "combined")
        .order_by(AIReport.as_of_date.desc(), AIReport.created_at.desc())
        .limit(1)
    ).first()

    extras: dict = {}
    if report and report.extras_json:
        try:
            extras = json.loads(report.extras_json)
        except json.JSONDecodeError:
            extras = {}

    return {
        "code": code,
        "name": stock.name or code,
        "close": latest.get("close"),
        "pct_chg": latest.get("pct_chg"),
        "turnover": latest.get("turnover"),
        "ma5": ma.get("ma5"),
        "ma10": ma.get("ma10"),
        "ma20": ma.get("ma20"),
        "ma60": ma.get("ma60"),
        "atr": indicators.get("atr", {}).get("atr") if isinstance(indicators.get("atr"), dict) else None,
        "boll_upper": boll.get("upper"),
        "boll_lower": boll.get("lower"),
        "verdict": report.verdict if report else None,
        "confidence": report.confidence if report else None,
        "summary": report.summary if report else None,
        "key_signals": extras.get("key_signals", []),
        "scenarios": extras.get("scenarios", []),
    }


@router.post("")
def generate_compare(payload: CompareRequest, session: Session = Depends(get_session)):
    if len(payload.codes) < 2:
        raise HTTPException(400, "至少选择 2 只股票")
    if len(payload.codes) > 6:
        raise HTTPException(400, "最多选择 6 只股票")

    codes_sorted = sorted(payload.codes)
    code_key = ",".join(codes_sorted)
    model = get_model_name()
    today = date.today()

    # 检查缓存
    if not payload.force:
        cached = session.exec(
            select(AIReport)
            .where(
                AIReport.code == code_key,
                AIReport.model == model,
                AIReport.horizon == "compare",
                AIReport.as_of_date == today,
            )
            .order_by(AIReport.created_at.desc())
            .limit(1)
        ).first()
        if cached:
            extras = {}
            if cached.extras_json:
                try:
                    extras = json.loads(cached.extras_json)
                except json.JSONDecodeError:
                    pass
            return {
                "id": cached.id,
                "codes": codes_sorted,
                "as_of_date": str(cached.as_of_date),
                "summary": cached.summary,
                "report_md": cached.report_md,
                "cached": True,
                **extras,
            }

    # 构建各票快照
    stocks_data = []
    for code in codes_sorted:
        snap = _build_stock_snapshot(session, code, model)
        if snap and not snap.get("empty"):
            stocks_data.append(snap)

    if len(stocks_data) < 2:
        raise HTTPException(400, "可分析的股票不足 2 只（部分无数据）")

    # 调用 AI
    result = analyze_compare(stocks_data)

    # 存储
    report = AIReport(
        code=code_key,
        as_of_date=today,
        model=model,
        horizon="compare",
        report_md=result.get("report_md", ""),
        verdict="neutral",
        summary=result.get("summary", ""),
        extras_json=json.dumps({
            "ranking": result.get("ranking", []),
            "allocation": result.get("allocation", []),
            "correlation_note": result.get("correlation_note", ""),
            "risk_note": result.get("risk_note", ""),
        }, ensure_ascii=False),
    )
    session.add(report)
    session.commit()
    session.refresh(report)

    return {
        "id": report.id,
        "codes": codes_sorted,
        "as_of_date": str(today),
        "summary": result.get("summary"),
        "report_md": result.get("report_md"),
        "ranking": result.get("ranking", []),
        "allocation": result.get("allocation", []),
        "correlation_note": result.get("correlation_note", ""),
        "risk_note": result.get("risk_note", ""),
        "cached": False,
    }


@router.get("/history")
def compare_history(session: Session = Depends(get_session)):
    model = get_model_name()
    reports = session.exec(
        select(AIReport)
        .where(AIReport.model == model, AIReport.horizon == "compare")
        .order_by(AIReport.created_at.desc())
        .limit(50)
    )
    items = []
    for r in reports:
        codes = r.code.split(",")
        # 取名字
        names = []
        for c in codes:
            s = session.get(Stock, c)
            names.append(s.name if s else c)
        items.append({
            "id": r.id,
            "codes": codes,
            "names": names,
            "as_of_date": str(r.as_of_date),
            "summary": r.summary,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M"),
        })
    return {"items": items}


@router.get("/{report_id}")
def compare_detail(report_id: int, session: Session = Depends(get_session)):
    report = session.get(AIReport, report_id)
    if not report or report.horizon != "compare":
        raise HTTPException(404, "对比报告不存在")

    extras: dict = {}
    if report.extras_json:
        try:
            extras = json.loads(report.extras_json)
        except json.JSONDecodeError:
            pass

    codes = report.code.split(",")
    names = []
    for c in codes:
        s = session.get(Stock, c)
        names.append(s.name if s else c)

    return {
        "id": report.id,
        "codes": codes,
        "names": names,
        "as_of_date": str(report.as_of_date),
        "summary": report.summary,
        "report_md": report.report_md,
        "created_at": report.created_at.strftime("%Y-%m-%d %H:%M"),
        **extras,
    }
