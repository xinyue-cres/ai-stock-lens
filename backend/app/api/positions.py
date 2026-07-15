"""持仓 API：手动录入 & 查询。不涉及交易执行。"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from app.db import get_session
from app.services import position_service

router = APIRouter(prefix="/api/positions", tags=["positions"])


class PositionPayload(BaseModel):
    code: str
    quantity: int
    cost_price: float
    opened_at: date
    note: str | None = None


@router.get("")
def list_all(session: Session = Depends(get_session)):
    return [position_service.summarize(session, p) for p in position_service.list_positions(session)]


@router.get("/{code}")
def get_one(code: str, session: Session = Depends(get_session)):
    pos = position_service.get_position(session, code)
    if not pos:
        raise HTTPException(404, "无持仓记录")
    return position_service.summarize(session, pos)


@router.post("")
def upsert(payload: PositionPayload, session: Session = Depends(get_session)):
    if payload.quantity < 0:
        raise HTTPException(400, "数量不能为负")
    if payload.cost_price <= 0:
        raise HTTPException(400, "成本价必须为正")
    pos = position_service.upsert_position(
        session,
        code=payload.code,
        quantity=payload.quantity,
        cost_price=payload.cost_price,
        opened_at=payload.opened_at,
        note=payload.note,
    )
    return position_service.summarize(session, pos)


@router.delete("/{code}")
def remove(code: str, session: Session = Depends(get_session)):
    ok = position_service.delete_position(session, code)
    return {"ok": ok}
