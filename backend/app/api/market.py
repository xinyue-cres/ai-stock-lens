from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlmodel import Session

from app.db import get_session
from app.services.market_service import get_market_context, INDEX_CODES

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/summary")
def market_summary(
    stock_pct: float | None = Query(None, description="个股今日涨跌幅，用于计算相对强弱"),
    session: Session = Depends(get_session),
):
    """大盘状态摘要：各指数今日/5日/20日涨跌幅 + 个股相对强弱。"""
    ctx = get_market_context(session)

    indices = []
    for code, name in INDEX_CODES.items():
        info = ctx.get(name, {})
        if info.get("empty"):
            continue
        indices.append({
            "code": code,
            "name": name,
            "pct_1d": info.get("pct_1d"),
            "pct_5d": info.get("pct_5d"),
            "pct_20d": info.get("pct_20d"),
            "latest_close": info.get("latest_close"),
        })

    # 大盘强弱判断（基于上证 + 创业板的平均日涨幅）
    day_pcts = [i["pct_1d"] for i in indices if i["pct_1d"] is not None]
    avg_pct = sum(day_pcts) / len(day_pcts) if day_pcts else 0

    if avg_pct >= 1.0:
        mood = "strong"
    elif avg_pct >= 0.2:
        mood = "positive"
    elif avg_pct >= -0.2:
        mood = "neutral"
    elif avg_pct >= -1.0:
        mood = "weak"
    else:
        mood = "panic"

    # 个股相对强弱
    relative = None
    if stock_pct is not None and day_pcts:
        diff = stock_pct - avg_pct
        if diff >= 2.0:
            relative = "far_outperform"
        elif diff >= 0.5:
            relative = "outperform"
        elif diff >= -0.5:
            relative = "inline"
        elif diff >= -2.0:
            relative = "underperform"
        else:
            relative = "far_underperform"

    return {
        "indices": indices,
        "mood": mood,
        "avg_pct_1d": round(avg_pct, 2),
        "stock_relative": relative,
    }
