from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.models.stock import Stock
from app.models.stock_group import StockGroup
from app.services.stock_service import get_group_ids

router = APIRouter(prefix="/api/groups", tags=["groups"])


class GroupCreate(BaseModel):
    name: str
    sort_order: int = 0


class GroupUpdate(BaseModel):
    name: str | None = None
    sort_order: int | None = None


@router.get("")
def list_groups(session: Session = Depends(get_session)):
    groups = list(session.exec(select(StockGroup).order_by(StockGroup.sort_order)))
    stocks = list(session.exec(select(Stock).where(Stock.is_watchlist == True)))  # noqa: E712
    counts: dict[int, int] = {}
    for s in stocks:
        for gid in get_group_ids(s):
            counts[gid] = counts.get(gid, 0) + 1
    return [
        {
            "id": g.id,
            "name": g.name,
            "sort_order": g.sort_order,
            "stock_count": counts.get(g.id, 0),
        }
        for g in groups
    ]


@router.post("")
def create_group(payload: GroupCreate, session: Session = Depends(get_session)):
    group = StockGroup(name=payload.name, sort_order=payload.sort_order)
    session.add(group)
    session.commit()
    session.refresh(group)
    return {"id": group.id, "name": group.name, "sort_order": group.sort_order}


@router.patch("/{group_id}")
def update_group(group_id: int, payload: GroupUpdate, session: Session = Depends(get_session)):
    group = session.get(StockGroup, group_id)
    if not group:
        raise HTTPException(404, "分组不存在")
    if payload.name is not None:
        group.name = payload.name
    if payload.sort_order is not None:
        group.sort_order = payload.sort_order
    session.add(group)
    session.commit()
    session.refresh(group)
    return {"id": group.id, "name": group.name, "sort_order": group.sort_order}


@router.delete("/{group_id}")
def delete_group(group_id: int, session: Session = Depends(get_session)):
    from app.services.stock_service import get_group_ids

    group = session.get(StockGroup, group_id)
    if not group:
        raise HTTPException(404, "分组不存在")
    import json as _json
    stocks = list(session.exec(select(Stock).where(Stock.is_watchlist == True)))  # noqa: E712
    affected = 0
    for s in stocks:
        ids = get_group_ids(s)
        if group_id in ids:
            new_ids = [gid for gid in ids if gid != group_id]
            s.group_ids = _json.dumps(new_ids) if new_ids else None
            session.add(s)
            affected += 1
    session.delete(group)
    session.commit()
    return {"ok": True, "released_stocks": affected}
