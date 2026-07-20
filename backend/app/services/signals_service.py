"""信号扫描服务：自选股列表信号聚合、stance/verdict/report-times 批量查询。"""
from __future__ import annotations

from datetime import date

from sqlmodel import Session, select

from app.indicators.engine import compute_all
from app.indicators.signals import scan_signals
from app.models.ai_report import AIReport
from app.models.ai_report_review import AIReportReview
from app.models.stock import Stock
from app.services.analysis_service import load_kline_df


def scan_watchlist_signals(session: Session, group_id: int | None = None) -> list[dict]:
    """遍历自选股，输出每只票当日的信号列表。"""
    from app.ai.client import get_model_name
    from app.models.stock_group import StockGroup
    from app.services import position_service, stock_service

    stmt = select(Stock).where(Stock.is_watchlist == True)  # noqa: E712
    stocks = list(session.exec(stmt))
    if group_id is not None:
        stocks = [s for s in stocks if group_id in stock_service.get_group_ids(s)]
    codes = [s.code for s in stocks]
    positions_by_code = position_service.get_positions_by_codes(session, codes)
    stance_map = _latest_stance_map(session, codes, get_model_name())
    ai_verdict_map = _latest_ai_verdict_map(session, codes, get_model_name())
    report_times_map = _latest_report_times_map(session, codes, get_model_name())

    group_names: dict[int, str] = {}
    group_ids = {s.group_id for s in stocks if s.group_id}
    if group_ids:
        for g in session.exec(select(StockGroup).where(StockGroup.id.in_(group_ids))):  # type: ignore[attr-defined]
            group_names[g.id] = g.name

    results: list[dict] = []
    for s in stocks:
        df = load_kline_df(session, s.code)
        pos = positions_by_code.get(s.code)
        position_summary = position_service.summarize(session, pos) if pos and pos.quantity > 0 else None
        stance_info = stance_map.get(s.code)
        ai_verdict = ai_verdict_map.get(s.code)

        base = {
            "code": s.code,
            "name": s.name,
            "market": s.market,
            "pinned": bool(s.pinned),
            "group_ids": stock_service.get_group_ids(s),
            "group_names": [group_names.get(gid, '') for gid in stock_service.get_group_ids(s) if gid in group_names],
            "note": s.note,
            "position": position_summary,
            "stance": stance_info,
            "ai_verdict": ai_verdict,
            "report_times": report_times_map.get(s.code, {}),
        }

        if df.empty:
            results.append({**base, "empty": True, "signals": [], "top_signal": None})
            continue
        indicators = compute_all(df)
        signals = scan_signals(indicators)
        latest_price = indicators.get("latest_price", {})
        results.append({
            **base,
            "as_of_date": indicators.get("as_of_date"),
            "close": latest_price.get("close"),
            "pct_chg": latest_price.get("pct_chg"),
            "signals": signals,
            "top_signal": signals[0] if signals else None,
        })
    return results


def get_previous_context(
    session: Session,
    code: str,
    horizon: str,
    model: str,
    exclude_as_of: date | None = None,
) -> dict | None:
    """取该 code 上一份同 horizon 报告及其最新复盘摘要，作为反思输入。"""
    stmt = select(AIReport).where(
        AIReport.code == code, AIReport.horizon == horizon, AIReport.model == model
    )
    if exclude_as_of is not None:
        stmt = stmt.where(AIReport.as_of_date != exclude_as_of)
    stmt = stmt.order_by(AIReport.as_of_date.desc(), AIReport.created_at.desc()).limit(1)
    prev = session.exec(stmt).first()
    if not prev:
        return None

    import json as _json

    extras: dict = {}
    if prev.extras_json:
        try:
            extras = _json.loads(prev.extras_json)
        except _json.JSONDecodeError:
            extras = {}

    latest = session.exec(
        select(AIReportReview)
        .where(AIReportReview.report_id == prev.id)
        .order_by(AIReportReview.review_date.desc())
        .limit(1)
    ).first()

    return {
        "as_of_date": str(prev.as_of_date),
        "verdict": prev.verdict,
        "confidence": prev.confidence,
        "summary": prev.summary,
        "scenarios": extras.get("scenarios", []),
        "latest_review": (
            {
                "review_date": str(latest.review_date),
                "days_after": latest.days_after,
                "verdict_hit": latest.verdict_hit,
                "price_change_pct": latest.price_change_pct,
                "triggered_count": latest.triggered_count,
                "total_scenarios": latest.total_scenarios,
            }
            if latest
            else None
        ),
    }


# --- 内部 helpers ---

def _latest_stance_map(session: Session, codes: list[str], model: str) -> dict[str, dict]:
    if not codes:
        return {}
    result: dict[str, dict] = {}
    plans = session.exec(
        select(AIReport)
        .where(
            AIReport.code.in_(codes),  # type: ignore[attr-defined]
            AIReport.model == model,
            AIReport.horizon == "action_plan",
        )
        .order_by(AIReport.code, AIReport.as_of_date.desc(), AIReport.created_at.desc())
    )
    for r in plans:
        if r.code not in result:
            result[r.code] = {
                "source": "trader",
                "value": r.verdict,
                "as_of": str(r.as_of_date),
            }
    missing = [c for c in codes if c not in result]
    if missing:
        reports = session.exec(
            select(AIReport)
            .where(
                AIReport.code.in_(missing),  # type: ignore[attr-defined]
                AIReport.model == model,
                AIReport.horizon == "combined",
            )
            .order_by(AIReport.code, AIReport.as_of_date.desc(), AIReport.created_at.desc())
        )
        for r in reports:
            if r.code not in result:
                result[r.code] = {
                    "source": "ai",
                    "value": r.verdict,
                    "as_of": str(r.as_of_date),
                }
    return result


def _latest_ai_verdict_map(session: Session, codes: list[str], model: str) -> dict[str, str]:
    if not codes:
        return {}
    result: dict[str, str] = {}
    reports = session.exec(
        select(AIReport)
        .where(
            AIReport.code.in_(codes),  # type: ignore[attr-defined]
            AIReport.model == model,
            AIReport.horizon == "combined",
        )
        .order_by(AIReport.code, AIReport.as_of_date.desc(), AIReport.created_at.desc())
    )
    for r in reports:
        if r.code not in result:
            result[r.code] = r.verdict
    return result


_REPORT_HORIZONS = ("combined", "anti_quant", "reflexivity", "action_plan")


def _latest_report_times_map(
    session: Session, codes: list[str], model: str
) -> dict[str, dict[str, str | None]]:
    if not codes:
        return {}
    result: dict[str, dict[str, str | None]] = {
        code: {h: None for h in _REPORT_HORIZONS} for code in codes
    }
    reports = session.exec(
        select(AIReport)
        .where(
            AIReport.code.in_(codes),  # type: ignore[attr-defined]
            AIReport.model == model,
            AIReport.horizon.in_(_REPORT_HORIZONS),  # type: ignore[attr-defined]
        )
        .order_by(AIReport.code, AIReport.horizon, AIReport.created_at.desc())
    )
    seen: set[tuple[str, str]] = set()
    for r in reports:
        key = (r.code, r.horizon)
        if key not in seen:
            seen.add(key)
            result[r.code][r.horizon] = r.created_at.strftime("%Y-%m-%d %H:%M")
    return result
