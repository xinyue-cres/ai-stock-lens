"""AI 打分点评/汇总路由：/summarize + /analyze-batch。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session

from app.ai.analyzer import AIAnalysisError, analyze_score_summary, analyze_stock_comment
from app.db import get_session
from app.features.scoring import _PEAK_CONF_STRONG
from app.models.stock_score import StockScore

from .models import AnalyzeBatchRequest, SummarizeRequest
from .utils import _query_scores, _scope_desc, _serialize, _sig

router = APIRouter()


@router.post("/summarize")
def summarize_scores(payload: SummarizeRequest, session: Session = Depends(get_session)):
    """对整个打分列表做 AI 总结（取各股分数最高的 top 5，教你怎么看待打分）。"""
    # 只取 top 5 避免 AI 上下文太长
    rows = _query_scores(session, scope=payload.scope, limit=5)
    items = [_serialize(r) for r in rows]
    context = _scope_desc(session, payload.scope, payload.group_ids)

    # 给 AI 的输入做精简，只保留打分核心指标
    for item in items:
        sig = _sig(StockScore(**{k: v for k, v in item.items() if k in StockScore.__fields__}))
        item["signal_summary"] = analyze_stock_comment(item)

    try:
        result = analyze_score_summary(items, context)
        return {"count": len(items), "context": context, "result": result}
    except AIAnalysisError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/analyze-batch")
def analyze_batch(payload: AnalyzeBatchRequest, session: Session = Depends(get_session)):
    """对当前打分列表逐只生成 AI 点评（每只独立总结，不做组对比）。

    并发逐只调用 AI，limit 上限 10，避免单次请求耗时过长。
    """
    limit = min(payload.limit, 10)
    rows = _query_scores(session, scope=payload.scope, limit=limit)
    if not rows:
        raise HTTPException(404, "当前范围还没有打分数据，请先触发扫描")
    items = [_serialize(r) for r in rows]

    def _one(it: dict) -> dict:
        try:
            return {**it, **analyze_stock_comment(it)}
        except AIAnalysisError as e:
            return {
                **it,
                "verdict": "分析失败",
                "summary": f"AI 调用失败：{e}",
                "score_comment": "",
                "key_point": "",
            }

    try:
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(_one, items))
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=502, detail="AI 批量点评失败") from None
    return {"count": len(results), "items": results}
