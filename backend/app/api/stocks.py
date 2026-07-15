from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.services import stock_service

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/search")
def search(q: str, session: Session = Depends(get_session)):
    results = stock_service.search_stocks(session, q)
    return [{"code": s.code, "name": s.name, "market": s.market} for s in results]
