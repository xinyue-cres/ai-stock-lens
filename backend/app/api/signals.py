from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.services import analysis_service

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("/today")
def signals_today(
    direction: str | None = None,
    category: str | None = None,
    session: Session = Depends(get_session),
):
    """扫描自选股当日信号。

    - direction: bullish | bearish | neutral，可选过滤
    - category: ma | oscillator | volume | pattern | strength，可选过滤
    """
    items = analysis_service.scan_watchlist_signals(session)

    if direction or category:
        for item in items:
            item["signals"] = [
                s
                for s in item["signals"]
                if (not direction or s["direction"] == direction)
                and (not category or s["category"] == category)
            ]
            item["top_signal"] = item["signals"][0] if item["signals"] else None

    return {
        "count": len(items),
        "items": items,
    }
