from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db import get_session
from app.services import compare_service

router = APIRouter(prefix="/api/compare", tags=["compare"])


@router.get("")
def compare(
    codes: list[str] = Query(default=[], description="股票代码列表，逗号分隔"),
    days: int = 120,
    session: Session = Depends(get_session),
):
    return compare_service.compare_stocks(session, codes, days=days)


@router.get("/watchlist")
def compare_watchlist(days: int = 120, session: Session = Depends(get_session)):
    codes = compare_service.list_watchlist_codes(session)
    return compare_service.compare_stocks(session, codes, days=days)
