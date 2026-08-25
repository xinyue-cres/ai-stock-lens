"""评分序列化/查询助手：把 ORM 行转成 API 字段，列表/详情/query 共用。"""
from __future__ import annotations

import json
from datetime import date, timedelta

from sqlmodel import Session, select

from app.features.scoring import _PEAK_CONF_STRONG
from app.models.stock import Stock
from app.models.stock_group import StockGroup
from app.models.stock_score import StockScore
from app.services.stock_service import get_group_ids, watchlist_codes_in_groups


def _serialize(r: StockScore) -> dict:
    """把 stock_score ORM 行转成 API 返回字典（前端 ScoreItem 结构）。"""
    sig = {}
    if r.components_json:
        try:
            comp = json.loads(r.components_json)
            sig = comp.get("signal") or {}
        except (json.JSONDecodeError, TypeError):
            pass
    return {
        "code": r.code,
        "name": r.name,
        "is_fund": r.is_fund,
        "scan_date": r.scan_date.isoformat(),
        "as_of_date": r.as_of_date.isoformat() if r.as_of_date else None,
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
        # 列表行展示用：DIF 斜率 + 当前状态 + 过峰信号（从 components 解析）
        "dif_slope": sig.get("dif_slope"),
        "dif_slope_dir": sig.get("dif_slope_dir"),
        "current_state": sig.get("current_state"),
        "peak_signal": sig.get("peak_signal"),
        "peak_conf": sig.get("peak_conf"),
        "scan_timeframe": r.scan_timeframe,
    }


def _sig(r: StockScore) -> dict:
    """从 components_json 里提取 signal 段（解析时用，出错返回空 dict）。"""
    if not r.components_json:
        return {}
    try:
        comp = json.loads(r.components_json)
        return comp.get("signal") or {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _serialize_combined(r) -> dict:
    """StockScoreCombined ORM 行 → API 返回结构（combined/list + combined/{code} 共用）。

    字段与前端 CombinedItem 一一对应；demote_reason/space_pct 等非主键字段
    用 getattr 兼容旧 schema（迁移期兜底）。
    """
    return {
        "code": r.code,
        "name": r.name,
        "is_fund": r.is_fund,
        "scan_date": str(r.scan_date),
        "as_of_date": str(r.as_of_date) if r.as_of_date else None,
        "weekly": {
            "total_score": r.weekly_total,
            "signal_score": r.weekly_signal,
            "trend_stage": r.weekly_stage,
            "peak_signal": r.weekly_peak_signal,
            "peak_conf": r.weekly_peak_conf,
        },
        "daily": {
            "total_score": r.daily_total,
            "signal_score": r.daily_signal,
            "trend_stage": r.daily_stage,
            "peak_signal": r.daily_peak_signal,
            "peak_conf": r.daily_peak_conf,
        },
        "combined_score": r.combined_score,
        "combined_stage": r.combined_stage,
        "can_entry": r.can_entry,
        "entry_reason": r.entry_reason,
        "trade_hint": r.trade_hint,
        "demote_reason": getattr(r, "demote_reason", None),
        "space_pct": getattr(r, "space_pct", None),
        "hist_golden_peak_pct": getattr(r, "hist_golden_peak_pct", None),
        "hist_golden_peak_median": getattr(r, "hist_golden_peak_median", None),
        "weekly_signal_gain_pct": getattr(r, "weekly_signal_gain_pct", None),
    }


def _scope_desc(session: Session, scope: str, group_ids: str | None) -> str:
    """把查看范围转成给 AI 说明的文字（summarize 场景）。仅展示用。"""
    if scope == "group" and group_ids:
        gids = [int(g) for g in group_ids.split(",") if g.strip().isdigit()]
        names = [g.name for g in session.exec(
            select(StockGroup).where(StockGroup.id.in_(gids))
        ).all()]
        return f"自选分组：{'、'.join(names) or group_ids}"
    if scope == "watchlist":
        return "全部自选股"
    return "全 A 股 + ETF"


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


def _latest_scan_date(session: Session, scope: str | None, timeframe: str = "daily") -> date | None:
    """当前范围对应的最近扫描批次日期（按需扫的，可能为空）。"""
    from sqlalchemy import func

    stmt = """
        SELECT MAX(scan_date) FROM stock_score
        WHERE scan_timeframe = :tf
          AND (:scope IS NULL OR scan_scope = :scope)
        """
    row = session.exec(
        select(func.max(StockScore.scan_date))
        .where(StockScore.scan_timeframe == timeframe)
        .where(StockScore.scan_scope == scope if scope else True)
    ).first()
    if row:
        # row 可能是 date / str / None
        if isinstance(row, date):
            return row
        try:
            from datetime import datetime as _dt
            return _dt.fromisoformat(str(row)).date()
        except (ValueError, TypeError):
            pass
    return None


_SORTABLE = {"total", "signal", "band", "dividend", "close", "pct_chg"}


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
    timeframe: str = "daily",
) -> list[StockScore]:
    """打分查询（list 与 summarize 共用同一套过滤/排序）。

    group_ids：逗号分隔的自选分组 id（任意匹配），传了只显示这些分组内的标的打分。
    scope：当前查看范围（all/watchlist/group），决定取哪个范围的最近扫描批次。
    timeframe：打分基于的周期（daily/weekly），按 (scan_date, scan_timeframe) 精确过滤。
    """
    sort_col = sort_by if sort_by in _SORTABLE else "total"
    col = getattr(StockScore, sort_col, StockScore.total_score)
    stmt = select(StockScore)
    # 只显示当前范围最近一次扫描批次，避免混入过期/旧算法残留行（scan_date 跨天时尤为关键）
    latest = _latest_scan_date(session, scope, timeframe)
    stmt = stmt.where(StockScore.scan_timeframe == timeframe)
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
