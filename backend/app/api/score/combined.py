"""综合评判路由：/combined/list + /combined/{code}。

综合的 daily+weekly 丢弃操作（Stage 为等）——都在 StockScoreCombined 表里按 composite_order 排序。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models.stock_score_combined import StockScoreCombined
from app.services.stock_service import watchlist_codes_in_groups

from .utils import _attach_watchlist_info

router = APIRouter()


@router.get("/combined/list")
def combined_list(
    session: Session = Depends(get_session),
    combined_stage: str | None = None,     # 只保留这 7 档顿范
    can_entry: bool | None = None,         # 只看可入手（strong_buy/buy/light_buy_entry）
    scope: str | None = None,              # 对齐最近批次；不传退化为全局最新 scan_date
    group_ids: str | None = None,          # 传唤「只保留这些组内的票」
    limit: int = 200,
):
    """综合评判列表。返回 (weekly + daily) 双腿核心字段 + 综合分 + 操作建议。"""
    from sqlalchemy import func

    # 取本 scope 最近一次批次（避免陈旧）
    stmt = select(StockScoreCombined)
    latest = session.exec(
        select(func.max(StockScoreCombined.scan_date)).where(
            StockScoreCombined.scan_scope == scope if scope in ("all", "watchlist", "group") else True
        )
    ).first()
    if latest:
        stmt = stmt.where(StockScoreCombined.scan_date == latest)
    if combined_stage:
        stmt = stmt.where(StockScoreCombined.combined_stage == combined_stage)
    if can_entry is not None:
        stmt = stmt.where(StockScoreCombined.can_entry == can_entry)
    # 用户传入 group_ids 只保留这些组内的票
    if group_ids:
        gids = [int(g) for g in group_ids.split(",") if g.strip().isdigit()]
        if gids:
            codes = watchlist_codes_in_groups(session, gids)
            if not codes:
                return []
            stmt = stmt.where(StockScoreCombined.code.in_(codes))  # type: ignore[attr-defined]
    stmt = stmt.order_by(StockScoreCombined.combined_score.desc()).limit(limit)
    rows = list(session.exec(stmt).all())
    items = [{
        "code": r.code,
        "name": r.name,
        "is_fund": r.is_fund,
        "scan_date": str(r.scan_date),
        "as_of_date": str(r.as_of_date) if r.as_of_date else None,
        "weekly": {
            "total_score": r.weekly_total,
            "signal_score": r.weekly_signal,
            "trend_stage": r.weekly_stage,
            "peak_signal": r.weekly_peak_signal,
            "peak_conf": r.weekly_peak_conf,
        },
        "daily": {
            "total_score": r.daily_total,
            "signal_score": r.daily_signal,
            "trend_stage": r.daily_stage,
            "peak_signal": r.daily_peak_signal,
            "peak_conf": r.daily_peak_conf,
        },
        "combined_score": r.combined_score,
        "combined_stage": r.combined_stage,
        "can_entry": r.can_entry,
        "entry_reason": r.entry_reason,
        "trade_hint": r.trade_hint,
        "demote_reason": getattr(r, "demote_reason", None),
        "space_pct": getattr(r, "space_pct", None),
        "hist_golden_peak_pct": getattr(r, "hist_golden_peak_pct", None),
        "hist_golden_peak_median": getattr(r, "hist_golden_peak_median", None),
        "weekly_signal_gain_pct": getattr(r, "weekly_signal_gain_pct", None),
    } for r in rows]
    # 附加 in_watchlist + group_ids（前端 StockList 视图联动）
    _attach_watchlist_info(session, items)
    return items


@router.get("/combined/{code}")
def combined_detail(code: str, session: Session = Depends(get_session)):
    """单只 combined 详情。"""
    r = session.get(StockScoreCombined, code)
    if not r:
        raise HTTPException(404, "该标的还没有综合评判记录")
    return {
        "code": r.code,
        "name": r.name,
        "is_fund": r.is_fund,
        "scan_date": str(r.scan_date),
        "as_of_date": str(r.as_of_date) if r.as_of_date else None,
        "weekly": {
            "total_score": r.weekly_total,
            "signal_score": r.weekly_signal,
            "trend_stage": r.weekly_stage,
            "peak_signal": r.weekly_peak_signal,
            "peak_conf": r.weekly_peak_conf,
        },
        "daily": {
            "total_score": r.daily_total,
            "signal_score": r.daily_signal,
            "trend_stage": r.daily_stage,
            "peak_signal": r.daily_peak_signal,
            "peak_conf": r.daily_peak_conf,
        },
        "combined_score": r.combined_score,
        "combined_stage": r.combined_stage,
        "can_entry": r.can_entry,
        "entry_reason": r.entry_reason,
        "trade_hint": r.trade_hint,
        "demote_reason": getattr(r, "demote_reason", None),
        "space_pct": getattr(r, "space_pct", None),
        "hist_golden_peak_pct": getattr(r, "hist_golden_peak_pct", None),
        "hist_golden_peak_median": getattr(r, "hist_golden_peak_median", None),
        "weekly_signal_gain_pct": getattr(r, "weekly_signal_gain_pct", None),
    }
