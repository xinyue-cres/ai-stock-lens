"""打分排行列表 + 扫描控制三个路由：/list, /scan, /scan/status, /scan/cancel。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.db import get_session
from app.features.scoring import _PEAK_CONF_STRONG
from app.services import scan as scan_service
from app.services.scoring_service import scan_market

from .models import ScanRequest
from .utils import _attach_watchlist_info, _query_scores, _serialize

router = APIRouter()


@router.get("/list")
def list_scores(
    session: Session = Depends(get_session),
    sort_by: str = "total",
    dir: str = "desc",
    limit: int = 100,
    min_score: float | None = None,
    can_entry: bool | None = None,
    stage: str | None = None,
    group_ids: str | None = None,  # 逗号分隔的自选分组 id，如 "9,10"（任意匹配）
    scope: str | None = None,  # all/watchlist/group，决定取哪个范围的最近扫描批次
    peak_filter: str = "all",  # all / exclude_up（排除上涨过峰）/ only_down（只看下跌过峰）
    timeframe: str = "daily",  # daily / weekly：查哪个周期的打分批次
):
    """打分排行列表。按综合分或任意子维度排序，支持过滤。

    peak_filter 在 Python 层过滤（peak_signal 存于 components_json，无法 SQL 过滤）：
    先多查一批再过滤，保证过滤后仍能取满 limit 条。
    timeframe 限 daily/weekly，其他值退化为 daily（防 SQL 注入 + 前端写错）。
    """
    tf = timeframe if timeframe in ("daily", "weekly") else "daily"
    # 过峰过滤时多查，Python 层过滤后再截断，避免过滤后不足 limit
    sql_limit = limit if peak_filter == "all" else max(limit * 5, 1000)
    rows = _query_scores(session, sort_by, dir, sql_limit, min_score, can_entry, stage,
                         group_ids, scope, timeframe=tf)
    items = [_serialize(r) for r in rows]
    if peak_filter == "exclude_up":
        # 排除"高位转折"强档信号（≥强档阈值）：包括
        # - 上涨过峰（dif≥0 + slope_up，顶部 DIF 高位转头）
        # - 顶部回落（dif>0 + slope_down，高位动能向下转）
        # 弱/中档多为涨势中正常柱缩，保留不误杀
        items = [
            i for i in items
            if not (i.get("peak_signal") in ("上涨过峰", "顶部回落")
                    and (i.get("peak_conf") or 0) >= _PEAK_CONF_STRONG)
        ]
    elif peak_filter == "only_down":
        # 看"低位转折"信号：下跌过峰（dif≤0+slope_down）+ 底部反转（dif<0+slope_up）
        items = [i for i in items if i.get("peak_signal") in ("下跌过峰", "底部反转")]
    items = items[:limit]
    _attach_watchlist_info(session, items)
    return items


@router.post("/scan")
def start_scan(payload: ScanRequest, session: Session = Depends(get_session)):
    """触发一次打分扫描（异步）。"""
    gids = payload.group_ids or ([payload.group_id] if payload.group_id is not None else None)
    tf = payload.timeframe if payload.timeframe in ("daily", "weekly") else "daily"
    return scan_market(
        session, scope=payload.scope, codes=payload.codes,
        force=payload.force, group_ids=gids, timeframe=tf,
    )


@router.get("/scan/status")
def scan_status():
    """当前扫描进度快照（前端轮询用）。"""
    return scan_service.get_scan_status()


@router.post("/scan/cancel")
def stop_scan():
    """请求取消进行中的扫描。"""
    return scan_service.cancel_scan()
