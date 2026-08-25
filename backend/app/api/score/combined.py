"""综合评判路由：/combined/list + /combined/{code}。

读 StockScoreCombined 表（daily+weekly 双腿由扫描 writer 合成），按 combined_score 降序返回。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.db import get_session
from app.models.stock_score_combined import StockScoreCombined
from app.services.stock_service import watchlist_codes_in_groups

from .utils import _attach_watchlist_info, _serialize_combined

router = APIRouter()


@router.get("/combined/list")
def combined_list(
    session: Session = Depends(get_session),
    combined_stage: str | None = None,     # 只保留这 1 档（12 档枚举见 combined_judge）
    can_entry: bool | None = None,         # 只看可入手（strong_buy/buy/deep_pullback_entry）
    scope: str | None = None,              # 对齐最近批次；不传退化为全局最新 scan_date
    group_ids: str | None = None,          # 传入「只保留这些组内的票」
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
    items = [_serialize_combined(r) for r in rows]
    # 附加 in_watchlist + group_ids（前端 StockList 视图联动）
    _attach_watchlist_info(session, items)
    return items


@router.get("/combined/{code}")
def combined_detail(code: str, session: Session = Depends(get_session)):
    """单只 combined 详情。"""
    r = session.get(StockScoreCombined, code)
    if not r:
        raise HTTPException(404, "该标的还没有综合评判记录")
    return _serialize_combined(r)
