"""单只打分/趋势详情路由：/{code} + /trend/{code}。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.db import get_session
from app.services.analysis_service import load_kline_df
from app.features.timeframe import to_bars
from app.features.trend_judge import judge_trend
from app.models.stock_score import StockScore

from .utils import _serialize

router = APIRouter()


@router.get("/{code}")
def score_detail(code: str, session: Session = Depends(get_session), timeframe: str = "daily"):
    """单只打分详情（含各维度明细 components.json）。"""
    tf = timeframe if timeframe in ("daily", "weekly") else "daily"
    row = session.get(StockScore, (code, tf))
    if not row:
        raise HTTPException(404, "该标的还没有打分记录，请先触发对应周期扫描")
    data = _serialize(row)
    data["timeframe"] = tf
    try:
        data["components"] = json.loads(row.components_json) if row.components_json else {}
    except json.JSONDecodeError:
        data["components"] = {}
    return data


@router.post("/trend/{code}")
def trend_detail(code: str, session: Session = Depends(get_session), timeframe: str = "daily"):
    """对单只标的重新跑一次趋势判断（详情页手动触发）。"""
    tf = timeframe if timeframe in ("daily", "weekly") else "daily"
    df = load_kline_df(session, code)
    if df.empty:
        raise HTTPException(404, "无法获取该标的 K 线")
    bars = to_bars(df, tf)
    row = session.get(StockScore, (code, tf))
    result = judge_trend(bars, signal_score=row.signal_score if row else None, timeframe=tf)
    return {"code": code, "timeframe": tf, **result}
