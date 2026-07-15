"""AI 报告复盘相关 API：查询分析日志 + 手动触发复盘补跑。"""
from __future__ import annotations

import json
from datetime import date

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

from app.db import get_session
from app.models.ai_report import AIReport
from app.models.ai_report_review import AIReportReview
from app.services.review_service import review_all_pending, review_report

router = APIRouter(prefix="/api", tags=["review"])


@router.get("/stocks/{code}/diary")
def get_diary(code: str, session: Session = Depends(get_session)) -> list[dict]:
    """分析日志：某股所有 AI 报告 + 各自复盘记录，按 as_of_date 倒序。"""
    reports = session.exec(
        select(AIReport).where(AIReport.code == code).order_by(AIReport.as_of_date.desc(), AIReport.created_at.desc())
    ).all()
    if not reports:
        return []

    ids = [r.id for r in reports if r.id is not None]
    reviews_by_report: dict[int, list[AIReportReview]] = {}
    if ids:
        rows = session.exec(
            select(AIReportReview).where(AIReportReview.report_id.in_(ids)).order_by(AIReportReview.review_date)
        ).all()
        for row in rows:
            reviews_by_report.setdefault(row.report_id, []).append(row)

    out: list[dict] = []
    for rep in reports:
        extras = {}
        if rep.extras_json:
            try:
                extras = json.loads(rep.extras_json)
            except json.JSONDecodeError:
                extras = {}
        reviews = reviews_by_report.get(rep.id or -1, [])
        latest = reviews[-1] if reviews else None
        out.append(
            {
                "report_id": rep.id,
                "code": rep.code,
                "as_of_date": str(rep.as_of_date),
                "created_at": rep.created_at.isoformat() if rep.created_at else None,
                "horizon": rep.horizon,
                "verdict": rep.verdict,
                "confidence": rep.confidence,
                "summary": rep.summary,
                "scenarios": extras.get("scenarios", []),
                "reflection": extras.get("reflection"),
                "latest_verdict_hit": latest.verdict_hit if latest else "pending",
                "latest_pct": latest.price_change_pct if latest else None,
                "reviews": [
                    {
                        "review_date": str(r.review_date),
                        "days_after": r.days_after,
                        "verdict_hit": r.verdict_hit,
                        "price_change_pct": r.price_change_pct,
                        "triggered_count": r.triggered_count,
                        "total_scenarios": r.total_scenarios,
                        "scenarios": json.loads(r.scenarios_json) if r.scenarios_json else [],
                        "notes": r.notes,
                    }
                    for r in reviews
                ],
            }
        )
    return out


@router.post("/stocks/{code}/diary/refresh")
def refresh_diary(code: str, session: Session = Depends(get_session)) -> dict:
    """为该股全部 AI 报告补齐复盘。"""
    reports = session.exec(select(AIReport).where(AIReport.code == code)).all()
    total_new = 0
    for rep in reports:
        created = review_report(session, rep)
        total_new += len(created)
    return {"code": code, "reports": len(reports), "new_reviews": total_new}


@router.post("/analysis/review/run")
def run_review_all(session: Session = Depends(get_session), up_to: date | None = None) -> dict:
    """全库复盘补跑（用于阶段 6 一次性回填）。"""
    return review_all_pending(session, up_to=up_to)
