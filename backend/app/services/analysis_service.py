"""分析服务：从库取 K 线 → 算指标 → 组合返回。

缓存说明：指纹用最近 5 行 K 线的字段内容 hash，只要 open/high/low/close/volume/
amount/turnover/pct_chg 任何一个改了指纹就变，无需手动 invalidate。回填、盘中
修正、增量同步等所有改动都会自动触发失效。
"""
from __future__ import annotations

import hashlib
import logging
from datetime import date, timedelta

import pandas as pd
from sqlmodel import Session, select

from app.indicators.engine import build_chart_series, compute_all
from app.indicators.signals import scan_signals
from app.indicators.weekly import aggregate_weekly
from app.models.ai_report import AIReport
from app.models.ai_report_review import AIReportReview
from app.models.kline import KlineDaily
from app.models.stock import Stock

logger = logging.getLogger(__name__)

# 进程内缓存：{code: (fingerprint, result_dict)}
# fingerprint = 最近 5 行关键字段的内容 hash，任何一个字段变化都失效
_ANALYSIS_CACHE: dict[str, tuple[str, dict]] = {}
_CACHE_MAX_SIZE = 200
_FINGERPRINT_TAIL = 5  # 只 hash 最后 N 行；老数据只在回填后短暂不一致，风险可控


def _fingerprint(df: pd.DataFrame) -> str:
    """基于最近 N 行内容的 hash。所有 OHLCV/turnover/pct_chg 变化都会改指纹。"""
    tail = df.tail(_FINGERPRINT_TAIL)[
        ["trade_date", "open", "high", "low", "close",
         "volume", "amount", "turnover", "pct_chg"]
    ]
    # 行数一起塞入以区分"最后 5 行相同但历史行数不同"的极端情况
    payload = f"{len(df)}|{tail.to_csv(index=False, header=False, na_rep='NULL')}"
    return hashlib.sha1(payload.encode()).hexdigest()


def load_kline_df(session: Session, code: str, days: int = 500) -> pd.DataFrame:
    end = date.today()
    start = end - timedelta(days=days * 2)
    stmt = (
        select(KlineDaily)
        .where(KlineDaily.code == code, KlineDaily.trade_date >= start)
        .order_by(KlineDaily.trade_date.asc())
    )
    rows = list(session.exec(stmt))
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(
        [
            {
                "trade_date": r.trade_date,
                "open": r.open,
                "high": r.high,
                "low": r.low,
                "close": r.close,
                "volume": r.volume,
                "amount": r.amount,
                "turnover": r.turnover,
                "pct_chg": r.pct_chg,
            }
            for r in rows
        ]
    )


def analyze(session: Session, code: str) -> dict:
    df = load_kline_df(session, code)
    stock = session.get(Stock, code)
    if df.empty:
        return {
            "code": code,
            "name": stock.name if stock else None,
            "empty": True,
            "message": "本地无数据，请先同步",
        }

    fingerprint = _fingerprint(df)
    cached = _ANALYSIS_CACHE.get(code)
    if cached and cached[0] == fingerprint:
        logger.debug("analyze cache hit for %s", code)
        return cached[1]

    indicators = compute_all(df)
    series = build_chart_series(df)
    signals = scan_signals(indicators)
    result = {
        "code": code,
        "name": stock.name if stock else None,
        "market": stock.market if stock else None,
        "indicators": indicators,
        "series": series,
        "signals": signals,
    }

    _ANALYSIS_CACHE[code] = (fingerprint, result)
    # 粗糙 LRU：超过阈值随便清一半
    if len(_ANALYSIS_CACHE) > _CACHE_MAX_SIZE:
        for k in list(_ANALYSIS_CACHE.keys())[: _CACHE_MAX_SIZE // 2]:
            _ANALYSIS_CACHE.pop(k, None)

    return result


def invalidate_analysis_cache(code: str | None = None) -> None:
    """通常不需要手动调 —— 指纹是内容 hash，K 线一变自动失效。保留仅为特殊场景（如
    调试、跨进程外部改库后强制刷新单进程缓存）。"""
    if code is None:
        _ANALYSIS_CACHE.clear()
    else:
        _ANALYSIS_CACHE.pop(code, None)


def build_ai_input(session: Session, code: str) -> tuple[dict, dict] | None:
    """给 AI 的输入：股票信息 + { 'daily': 日线指标, 'weekly': 周线指标, 'market': 大盘上下文 }。"""
    df = load_kline_df(session, code)
    if df.empty:
        return None
    stock = session.get(Stock, code)
    stock_info = {
        "code": code,
        "name": stock.name if stock else "-",
        "market": stock.market if stock else "-",
    }
    daily_ind = compute_all(df)
    weekly_df = aggregate_weekly(df)
    weekly_ind = compute_all(weekly_df) if not weekly_df.empty else {"empty": True}

    # 大盘上下文（无则为空 dict，不阻塞主流程）
    try:
        from app.services.market_service import get_market_context

        market = get_market_context(session)
    except Exception:  # noqa: BLE001
        market = {}

    return stock_info, {
        "daily": daily_ind,
        "weekly": weekly_ind,
        "market": market,
        "as_of_date": daily_ind.get("as_of_date"),
    }


def scan_watchlist_signals(session: Session, group_id: int | None = None) -> list[dict]:
    """遍历自选股，输出每只票当日的信号列表。"""
    from app.ai.client import get_model_name
    from app.models.stock_group import StockGroup
    from app.services import position_service, stock_service

    stmt = select(Stock).where(Stock.is_watchlist == True)  # noqa: E712
    stocks = list(session.exec(stmt))
    if group_id is not None:
        stocks = [s for s in stocks if group_id in stock_service.get_group_ids(s)]
    codes = [s.code for s in stocks]
    positions_by_code = position_service.get_positions_by_codes(session, codes)
    stance_map = _latest_stance_map(session, codes, get_model_name())
    ai_verdict_map = _latest_ai_verdict_map(session, codes, get_model_name())

    group_names: dict[int, str] = {}
    group_ids = {s.group_id for s in stocks if s.group_id}
    if group_ids:
        for g in session.exec(select(StockGroup).where(StockGroup.id.in_(group_ids))):  # type: ignore[attr-defined]
            group_names[g.id] = g.name

    results: list[dict] = []
    for s in stocks:
        df = load_kline_df(session, s.code)
        pos = positions_by_code.get(s.code)
        position_summary = position_service.summarize(session, pos) if pos and pos.quantity > 0 else None
        stance_info = stance_map.get(s.code)
        ai_verdict = ai_verdict_map.get(s.code)

        base = {
            "code": s.code,
            "name": s.name,
            "market": s.market,
            "pinned": bool(s.pinned),
            "group_ids": stock_service.get_group_ids(s),
            "group_names": [group_names.get(gid, '') for gid in stock_service.get_group_ids(s) if gid in group_names],
            "note": s.note,
            "position": position_summary,
            "stance": stance_info,
            "ai_verdict": ai_verdict,
        }

        if df.empty:
            results.append({**base, "empty": True, "signals": [], "top_signal": None})
            continue
        indicators = compute_all(df)
        signals = scan_signals(indicators)
        latest_price = indicators.get("latest_price", {})
        results.append({
            **base,
            "as_of_date": indicators.get("as_of_date"),
            "close": latest_price.get("close"),
            "pct_chg": latest_price.get("pct_chg"),
            "signals": signals,
            "top_signal": signals[0] if signals else None,
        })
    return results


def _latest_stance_map(session: Session, codes: list[str], model: str) -> dict[str, dict]:
    """一次性拉自选股列表每只票"最新的立场"：
    优先 action_plan.overall_stance，其次 combined 报告的 verdict。
    返回 {code: {source: "trader"|"ai", value: str, as_of: str}}"""
    if not codes:
        return {}
    result: dict[str, dict] = {}
    # 一批查 action_plan
    plans = session.exec(
        select(AIReport)
        .where(
            AIReport.code.in_(codes),  # type: ignore[attr-defined]
            AIReport.model == model,
            AIReport.horizon == "action_plan",
        )
        .order_by(AIReport.code, AIReport.as_of_date.desc(), AIReport.created_at.desc())
    )
    for r in plans:
        if r.code not in result:
            result[r.code] = {
                "source": "trader",
                "value": r.verdict,
                "as_of": str(r.as_of_date),
            }
    # 缺失的 fallback 到 combined verdict
    missing = [c for c in codes if c not in result]
    if missing:
        reports = session.exec(
            select(AIReport)
            .where(
                AIReport.code.in_(missing),  # type: ignore[attr-defined]
                AIReport.model == model,
                AIReport.horizon == "combined",
            )
            .order_by(AIReport.code, AIReport.as_of_date.desc(), AIReport.created_at.desc())
        )
        for r in reports:
            if r.code not in result:
                result[r.code] = {
                    "source": "ai",
                    "value": r.verdict,
                    "as_of": str(r.as_of_date),
                }
    return result


def _latest_ai_verdict_map(session: Session, codes: list[str], model: str) -> dict[str, str]:
    """一次性拉所有自选股最新 combined 报告的 verdict。独立于 stance_map 返回。"""
    if not codes:
        return {}
    result: dict[str, str] = {}
    reports = session.exec(
        select(AIReport)
        .where(
            AIReport.code.in_(codes),  # type: ignore[attr-defined]
            AIReport.model == model,
            AIReport.horizon == "combined",
        )
        .order_by(AIReport.code, AIReport.as_of_date.desc(), AIReport.created_at.desc())
    )
    for r in reports:
        if r.code not in result:
            result[r.code] = r.verdict
    return result


def get_previous_context(
    session: Session,
    code: str,
    horizon: str,
    model: str,
    exclude_as_of: date | None = None,
) -> dict | None:
    """取该 code 上一份同 horizon 报告及其最新复盘摘要，作为反思输入。

    exclude_as_of：排除该日期的报告（避免"用今天的旧版反思今天的新版"）。
    """
    stmt = select(AIReport).where(
        AIReport.code == code, AIReport.horizon == horizon, AIReport.model == model
    )
    if exclude_as_of is not None:
        stmt = stmt.where(AIReport.as_of_date != exclude_as_of)
    stmt = stmt.order_by(AIReport.as_of_date.desc(), AIReport.created_at.desc()).limit(1)
    prev = session.exec(stmt).first()
    if not prev:
        return None

    import json as _json

    extras: dict = {}
    if prev.extras_json:
        try:
            extras = _json.loads(prev.extras_json)
        except _json.JSONDecodeError:
            extras = {}

    latest = session.exec(
        select(AIReportReview)
        .where(AIReportReview.report_id == prev.id)
        .order_by(AIReportReview.review_date.desc())
        .limit(1)
    ).first()

    return {
        "as_of_date": str(prev.as_of_date),
        "verdict": prev.verdict,
        "confidence": prev.confidence,
        "summary": prev.summary,
        "scenarios": extras.get("scenarios", []),
        "latest_review": (
            {
                "review_date": str(latest.review_date),
                "days_after": latest.days_after,
                "verdict_hit": latest.verdict_hit,
                "price_change_pct": latest.price_change_pct,
                "triggered_count": latest.triggered_count,
                "total_scenarios": latest.total_scenarios,
            }
            if latest
            else None
        ),
    }
