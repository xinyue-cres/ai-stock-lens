"""选股打分 API：打分排行、单只详情、扫描控制、趋势判断。"""
from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import Session, select

from app.ai.analyzer import AIAnalysisError, analyze_score_summary, analyze_stock_comment
from app.config import get_settings
from app.datasource.router import get_data_router
from app.db import get_session
from app.features.stock_scorer import _PEAK_CONF_STRONG
from app.features.trend_judge import judge_trend
from app.models.stock import Stock
from app.models.stock_group import StockGroup
from app.models.stock_score import StockScore
from app.services import scoring_service
from app.services.analysis_service import load_kline_df
from app.services.stock_service import watchlist_codes_in_groups, get_group_ids

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/score", tags=["score"])

_SORTABLE = {"total", "signal", "band", "dividend", "close", "pct_chg"}


class ScanRequest(BaseModel):
    scope: str = "all"  # all | watchlist
    codes: list[str] | None = None
    force: bool = False
    group_id: int | None = None  # 兼容旧字段：单个分组
    group_ids: list[int] | None = None  # scope=watchlist 时按多个自选分组过滤（任意匹配）


class SummarizeRequest(BaseModel):
    scope: str = "all"  # all | watchlist | group（仅用于给 AI 说明查看范围）
    group_ids: str | None = None
    sort_by: str = "total"
    dir: str = "desc"
    limit: int = 15
    can_entry: bool | None = None


class AnalyzeBatchRequest(BaseModel):
    scope: str = "all"
    group_ids: str | None = None
    sort_by: str = "total"
    dir: str = "desc"
    limit: int = 10
    can_entry: bool | None = None


def _serialize(r: StockScore) -> dict:
    return {
        "code": r.code,
        "name": r.name,
        "is_fund": r.is_fund,
        "scan_date": str(r.scan_date),
        "as_of_date": str(r.as_of_date) if r.as_of_date else None,
        "total_score": r.total_score,
        "signal_score": r.signal_score,
        "band_score": r.band_score,
        "dividend_score": r.dividend_score,
        "close": r.close,
        "pct_chg": r.pct_chg,
        "turnover": r.turnover,
        "hist_vol": r.hist_vol,
        "adx": r.adx,
        "dividend_yield": r.dividend_yield,
        "trend_stage": r.trend_stage,
        "can_entry": r.can_entry,
        "entry_reason": r.entry_reason,
        # 列表行展示用：DIF 斜率 + 当前状态（从 components 解析，仅作参考展示）
        "dif_slope": (_sig(r).get("dif_slope")),
        "dif_slope_dir": (_sig(r).get("dif_slope_dir")),
        "current_state": (_sig(r).get("current_state")),
        # 过峰信号（bar|acc_z 触发 + 置信度评级）：上涨过峰/下跌过峰/涨势延续/跌势延续 + 置信度
        "peak_signal": (_sig(r).get("peak_signal")),
        "peak_conf": (_sig(r).get("peak_conf")),
    }


def _sig(r: StockScore) -> dict:
    """从 components_json 解析 signal 子项（列表行展示参考指标用）。"""
    if not r.components_json:
        return {}
    try:
        comp = json.loads(r.components_json)
    except (json.JSONDecodeError, TypeError):
        return {}
    sig = comp.get("signal") if isinstance(comp, dict) else None
    return sig if isinstance(sig, dict) else {}


def _attach_watchlist_info(session: Session, items: list[dict]) -> None:
    """给打分列表批量补 in_watchlist + group_ids（选股页跳工作台分组视图用）。

    StockScore 表不含分组关系，需从 Stock 表按 code 批量反查；避免 N+1 逐条查询。
    """
    codes = [i["code"] for i in items]
    if not codes:
        return
    stocks = session.exec(select(Stock).where(Stock.code.in_(codes))).all()  # type: ignore[attr-defined]
    wl = {s.code: s for s in stocks if s.is_watchlist}
    for i in items:
        s = wl.get(i["code"])
        if s:
            i["in_watchlist"] = True
            i["group_ids"] = get_group_ids(s)
        else:
            i["in_watchlist"] = False
            i["group_ids"] = []


def _latest_scan_date(session: Session, scope: str | None) -> date | None:
    """当前范围对应的最近扫描批次日期。

    按 scan_scope 精确匹配（全 A/自选/分组各自的最新批次，互不串——修复
    "切全 A 却显示上次分组扫描批次"）；该范围无记录（如旧数据未标 scope）时回退全局最新。
    """
    if scope and scope in ("all", "watchlist", "group"):
        latest = session.exec(
            select(func.max(StockScore.scan_date)).where(StockScore.scan_scope == scope)
        ).first()
        if latest:
            return latest
    return session.exec(select(func.max(StockScore.scan_date))).first()


def _query_scores(
    session: Session,
    sort_by: str = "total",
    dir: str = "desc",
    limit: int = 100,
    min_score: float | None = None,
    can_entry: bool | None = None,
    stage: str | None = None,
    group_ids: str | None = None,
    scope: str | None = None,
) -> list[StockScore]:
    """打分查询（list 与 summarize 共用同一套过滤/排序）。

    group_ids：逗号分隔的自选分组 id（任意匹配），传了只显示这些分组内的标的打分。
    scope：当前查看范围（all/watchlist/group），决定取哪个范围的最近扫描批次。
    """
    sort_col = sort_by if sort_by in _SORTABLE else "total"
    col = getattr(StockScore, sort_col, StockScore.total_score)
    stmt = select(StockScore)
    # 只显示当前范围最近一次扫描批次，避免混入过期/旧算法残留行（scan_date 跨天时尤为关键）
    latest = _latest_scan_date(session, scope)
    if latest:
        stmt = stmt.where(StockScore.scan_date == latest)
    if min_score is not None:
        stmt = stmt.where(StockScore.total_score >= min_score)
    if can_entry is not None:
        stmt = stmt.where(StockScore.can_entry == can_entry)
    if stage:
        stmt = stmt.where(StockScore.trend_stage == stage)
    if group_ids:
        gids = [int(g) for g in group_ids.split(",") if g.strip().isdigit()]
        if gids:
            codes = watchlist_codes_in_groups(session, gids)
            if not codes:
                return []
            stmt = stmt.where(StockScore.code.in_(codes))
    stmt = stmt.order_by(col.desc() if dir == "desc" else col.asc()).limit(limit)
    return list(session.exec(stmt).all())


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
):
    """打分排行列表。按综合分或任意子维度排序，支持过滤。

    group_ids 传了则只显示这些自选分组内的标的打分（多选，命中任一即显示）。
    peak_filter 在 Python 层过滤（peak_signal 存于 components_json，无法 SQL 过滤）：
    先多查一批再过滤，保证过滤后仍能取满 limit 条。
    """
    # 过峰过滤时多查，Python 层过滤后再截断，避免过滤后不足 limit
    sql_limit = limit if peak_filter == "all" else max(limit * 5, 1000)
    rows = _query_scores(session, sort_by, dir, sql_limit, min_score, can_entry, stage, group_ids, scope)
    items = [_serialize(r) for r in rows]
    if peak_filter == "exclude_up":
        # 只排除强档及以上（≥51）的上涨过峰；弱/中档多为涨势中正常柱缩（历史占比 ~28%），保留不误杀
        items = [
            i for i in items
            if not (i.get("peak_signal") == "上涨过峰" and (i.get("peak_conf") or 0) >= _PEAK_CONF_STRONG)
        ]
    elif peak_filter == "only_down":
        items = [i for i in items if i.get("peak_signal") == "下跌过峰"]
    items = items[:limit]
    _attach_watchlist_info(session, items)
    return items


@router.get("/scan/status")
def scan_status():
    return scoring_service.get_scan_status()


@router.post("/scan")
def start_scan(payload: ScanRequest, session: Session = Depends(get_session)):
    gids = payload.group_ids or ([payload.group_id] if payload.group_id is not None else None)
    return scoring_service.scan_market(
        session, scope=payload.scope, codes=payload.codes,
        force=payload.force, group_ids=gids,
    )


@router.post("/scan/cancel")
def stop_scan():
    return scoring_service.cancel_scan()


def _scope_desc(session: Session, scope: str, group_ids: str | None) -> str:
    """把查看范围转成给 AI 的一句话描述。"""
    if scope == "group" and group_ids:
        gids = [int(g) for g in group_ids.split(",") if g.strip().isdigit()]
        names = [g.name for g in session.exec(
            select(StockGroup).where(StockGroup.id.in_(gids))
        ).all()]
        return f"自选分组：{'、'.join(names) or group_ids}"
    if scope == "watchlist":
        return "全部自选股"
    return "全 A 股 + ETF"


@router.post("/summarize")
def summarize_scores(payload: SummarizeRequest, session: Session = Depends(get_session)):
    """对当前打分列表做 AI 汇总（独立按钮，不参与扫描流程）。

    复用与列表一致的过滤/排序，取 top N 标的交给 AI 二次解读。
    """
    rows = _query_scores(
        session, payload.sort_by, payload.dir, payload.limit,
        can_entry=payload.can_entry, group_ids=payload.group_ids,
        scope=payload.scope,
    )
    if not rows:
        raise HTTPException(404, "当前范围还没有打分数据，请先触发扫描")
    items = [_serialize(r) for r in rows]
    context = _scope_desc(session, payload.scope, payload.group_ids)
    try:
        result = analyze_score_summary(items, context)
    except AIAnalysisError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e
    return {"scope": payload.scope, "count": len(items), **result}


@router.post("/analyze-batch")
def analyze_batch(payload: AnalyzeBatchRequest, session: Session = Depends(get_session)):
    """对当前打分列表逐只生成 AI 点评（每只独立总结，不做组对比）。

    并发逐只调用 AI，limit 上限 10，避免单次请求耗时过长。
    """
    limit = min(payload.limit, 10)
    rows = _query_scores(
        session, payload.sort_by, payload.dir, limit,
        can_entry=payload.can_entry, group_ids=payload.group_ids,
        scope=payload.scope,
    )
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
        logger.exception("AI 批量点评失败")
        raise HTTPException(status_code=502, detail="AI 批量点评失败") from None
    return {"count": len(results), "items": results}


@router.get("/{code}")
def score_detail(code: str, session: Session = Depends(get_session)):
    """单只打分详情（含各维度明细 components）。"""
    row = session.get(StockScore, code)
    if not row:
        raise HTTPException(404, "该标的还没有打分记录，请先触发扫描")
    data = _serialize(row)
    try:
        data["components"] = json.loads(row.components_json) if row.components_json else {}
    except json.JSONDecodeError:
        data["components"] = {}
    return data


@router.post("/trend/{code}")
def trend_detail(code: str, session: Session = Depends(get_session)):
    """对单只标的重新跑一次趋势判断（详情页手动触发）。"""
    df = load_kline_df(session, code)
    if df.empty:
        settings = get_settings()
        end = date.today()
        start = end - timedelta(days=settings.scan_kline_days)
        df = get_data_router().fetch_stock_daily(code, start, end)
    if df.empty:
        raise HTTPException(404, "无法获取该标的 K 线")
    # 传入金叉延续分，保持与扫描口径一致（金叉驱动趋势判断）
    row = session.get(StockScore, code)
    result = judge_trend(df, signal_score=row.signal_score if row else None)
    return {"code": code, **result}
