"""选股扫描编排：候选池 → 并发拉 K 线 → 打分 + 趋势判断 → upsert StockScore。

关键设计：
- 扫描不落 K 线库，只用 DataRouter 直拉近 ~500 根日线，内存计算后只写 StockScore。
- ThreadPoolExecutor 并发 + 每请求 sleep 限流，防东财封禁。
- 全局 _scan_state 供前端轮询进度；进程级锁保证单扫描实例；支持取消。
- 每个 worker 用独立的 SQLAlchemy Session（Session 不是线程安全的）。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pandas as pd
from sqlmodel import Session, select

from app.config import get_settings
from app.datasource.base_provider import is_fund_code
from app.datasource.router import get_data_router
from app.db import engine
from app.features.stock_scorer import compute_indicator_cache, score_stock
from app.features.trend_judge import judge_trend
from app.models.stock import Stock
from app.models.stock_score import StockScore
from app.services.dividend_service import load_dividend_map
from app.services.stock_service import watchlist_codes_in_groups

logger = logging.getLogger(__name__)

_scan_lock = threading.Lock()
_scan_state: dict = {
    "running": False,
    "scope": None,
    "total": 0,
    "done": 0,
    "failed": 0,
    "current": None,
    "started_at": None,
    "finished_at": None,
    "cancel_requested": False,
}


def _state(mutate: bool = False) -> dict:
    if mutate:
        return _scan_state
    with _scan_lock:
        return dict(_scan_state)


def get_scan_status() -> dict:
    """当前扫描进度（前端轮询用）。"""
    with _scan_lock:
        return dict(_scan_state)


def cancel_scan() -> dict:
    """请求取消进行中的扫描。"""
    with _scan_lock:
        _scan_state["cancel_requested"] = True
        running = _scan_state["running"]
    return {"ok": True, "running": running}


def _parse_as_of(value) -> date | None:
    """把 trade_date（可能是 date/str/Timestamp）规整成 date。"""
    if isinstance(value, date):
        return value
    try:
        return pd.to_datetime(value).date()
    except Exception:  # noqa: BLE001
        return None


def _build_pool(session: Session, scope: str, codes: list[str] | None,
                group_ids: list[int] | None = None) -> tuple[list[str], dict[str, str]]:
    """构建候选池与名称 map。scope=watchlist 时可按 group_ids 过滤到若干个自选分组（任意匹配）。"""
    router = get_data_router()
    if codes:
        candidates = list(codes)
        name_map = {}
        for c in candidates:
            row = session.get(Stock, c)
            if row:
                name_map[c] = row.name
        # 补齐不在 Stock 表里的代码名称（从全市场列表）
        missing = [c for c in candidates if c not in name_map]
        if missing:
            try:
                for si in router.get_stock_list():
                    if si.code in missing:
                        name_map[si.code] = si.name
            except Exception:  # noqa: BLE001
                logger.warning("拉取股票列表补名称失败")
        for c in candidates:
            name_map.setdefault(c, c)
        return candidates, name_map
    if scope in ("watchlist", "group"):
        # watchlist=全部自选；group=按所选分组过滤（group_ids 为空时退化为全部自选）
        codes = watchlist_codes_in_groups(session, group_ids)
        stocks = session.exec(select(Stock).where(Stock.is_watchlist == True)).all()  # noqa: E712
        return sorted(codes), {s.code: s.name for s in stocks}
    # all：A 股 + ETF/LOF
    stock_infos = router.get_stock_list()
    return [si.code for si in stock_infos], {si.code: si.name for si in stock_infos}


def _fetch_kline(code: str, settings) -> object | None:
    """拉近 ~500 根日线（优先用库内 K 线缓存，缺失才拉网络）。带限流 sleep。"""
    try:
        end = date.today()
        start = end - timedelta(days=settings.scan_kline_days)  # 约 2 自然年 ≈ 500 交易日
        cached = _load_cached_kline(code, start)
        if cached is not None:
            return cached
        df = get_data_router().fetch_stock_daily(code, start, end)
        # 请求间限流，防数据源封禁；当前东财不可用走新浪兜底，可更激进。
        # 若东财恢复后被限流，可回调到 0.05~0.08
        time.sleep(0.02)
        return df
    except Exception:  # noqa: BLE001
        logger.warning("拉取 %s K 线失败", code)
        return None


def _load_cached_kline(code: str, start: date) -> object | None:
    """从 KlineDaily 读 K 线缓存；覆盖扫描窗口（≥400 根）直接返回，否则 None 走网络拉取。

    复权口径与扫描一致（KlineDaily 由 sync 用 qfq 写入，扫描也用 qfq），可安全复用；
    已同步/自选过的股票扫描不再重复拉网络。
    """
    from app.models.kline import KlineDaily

    with Session(engine) as s:
        rows = list(s.exec(
            select(KlineDaily)
            .where(KlineDaily.code == code, KlineDaily.trade_date >= start)
            .order_by(KlineDaily.trade_date.asc())
        ))
    if len(rows) < 400:
        return None
    return pd.DataFrame([
        {
            "trade_date": r.trade_date, "open": r.open, "high": r.high,
            "low": r.low, "close": r.close, "volume": r.volume,
            "amount": r.amount, "turnover": r.turnover, "pct_chg": r.pct_chg,
        }
        for r in rows
    ])


def _upsert(session: Session, code: str, name: str, scored: dict, trend: dict,
            scan_date: date, as_of_date: date | None, scope: str) -> None:
    row = session.get(StockScore, code)
    if row is None:
        row = StockScore(code=code)
    row.name = name
    row.is_fund = is_fund_code(code)
    row.scan_date = scan_date
    row.scan_scope = scope
    row.as_of_date = as_of_date
    row.total_score = scored["total_score"]
    row.signal_score = scored["signal_score"]
    row.band_score = scored["band_score"]
    row.dividend_score = scored["dividend_score"]
    row.close = scored["close"]
    row.pct_chg = scored["pct_chg"]
    row.turnover = scored["turnover"]
    row.hist_vol = scored["hist_vol"]
    row.adx = scored["adx"]
    row.dividend_yield = scored["dividend_yield"]
    row.trend_stage = trend.get("trend_stage")
    row.can_entry = trend.get("can_entry")
    row.entry_reason = trend.get("entry_reason")
    row.components_json = json.dumps({
        **scored["components"],
        "trend": {"key_prices": trend.get("key_prices"), "indicators": trend.get("indicators")},
    }, ensure_ascii=False)
    session.add(row)
    session.commit()


def _build_plan(session: Session, scope: str, codes: list[str] | None,
                group_ids: list[int] | None, force: bool) -> dict:
    """同步构建扫描计划：候选池 + 当日去重。

    返回 {todo, name_map, total, skipped}；todo 为空（全部已扫描）时同时把
    running 置回 False。候选池构建失败会抛异常（调用方负责复位状态）。
    """
    today = date.today()
    try:
        candidates, name_map = _build_pool(session, scope, codes, group_ids)
        if not force:
            already = set(session.exec(
                select(StockScore.code).where(StockScore.scan_date == today)
            ).all())
            todo = [c for c in candidates if c not in already]
        else:
            todo = list(candidates)

        with _scan_lock:
            _scan_state["total"] = len(todo)

        if not todo:
            with _scan_lock:
                _scan_state.update(running=False, finished_at=today.isoformat())

        return {"todo": todo, "name_map": name_map, "total": len(todo), "skipped": len(candidates) - len(todo)}
    except Exception:  # noqa: BLE001
        with _scan_lock:
            _scan_state.update(running=False, finished_at=date.today().isoformat())
        raise


def _run_scan(todo: list[str], name_map: dict[str, str], settings, today: date, scope: str) -> None:
    """后台线程执行实际打分（启动后立即返回，不阻塞 POST）。

    股息 map 在后台线程内用独立 Session 拉取：
    - 请求级 session 已随 POST 返回被关闭，不能复用（复用会抛异常→扫描静默中断 done=0）；
    - 放后台还能避免全市场扫描拉 3 年分红全表时阻塞 POST（超过 30s 前端报错）。
    """
    try:
        try:
            with Session(engine) as div_s:
                dividend_map = load_dividend_map(div_s, todo)
        except Exception:  # noqa: BLE001
            logger.warning("预加载股息 map 失败，按无股息处理")
            dividend_map = {}

        def _process(code: str) -> None:
            if _scan_state["cancel_requested"]:
                return
            failed = True
            try:
                df = _fetch_kline(code, settings)
                if df is not None and not df.empty:
                    # 指标只算一次，score_stock 与 judge_trend 复用（避免重复算 MACD/ADX/BOLL/Risk）
                    cache = compute_indicator_cache(df)
                    scored = score_stock(df, dividend_map.get(code), is_fund_code(code), cache=cache)
                    if scored is not None:
                        trend = judge_trend(df, signal_score=scored["signal_score"], cache=cache)
                        as_of_date = _parse_as_of(df["trade_date"].iloc[-1])
                        with Session(engine) as s:
                            _upsert(s, code, name_map.get(code, code), scored, trend, today, as_of_date, scope)
                        failed = False
            except Exception:  # noqa: BLE001
                logger.exception("打分失败 %s", code)
            with _scan_lock:
                _scan_state["done"] += 1
                if failed:
                    _scan_state["failed"] += 1
                _scan_state["current"] = code

        with ThreadPoolExecutor(max_workers=settings.scan_concurrency) as pool:
            for _ in pool.map(_process, todo):
                pass
    finally:
        with _scan_lock:
            _scan_state.update(running=False, finished_at=date.today().isoformat())


def scan_market(session: Session, scope: str = "all", codes: list[str] | None = None,
                force: bool = False, group_ids: list[int] | None = None) -> dict:
    """触发一次全市场/自选股扫描。已在 running 时直接返回不重复启动。

    group_ids：scope=watchlist/group 时可传多个自选分组 id，只扫这些分组内的自选股（任意匹配）。

    异步设计：同步构建候选池（拿到 total）后立即返回，实际打分放后台线程执行。
    全市场扫描可达数分钟，不能阻塞 POST（前端 30s 超时）。
    """
    with _scan_lock:
        if _scan_state["running"]:
            return {"started": False, "reason": "已有扫描进行中", "total": _scan_state["total"]}
        _scan_state.update(
            running=True, scope=scope, total=0, done=0, failed=0,
            current=None, started_at=date.today().isoformat(),
            finished_at=None, cancel_requested=False,
        )

    settings = get_settings()
    today = date.today()
    plan = _build_plan(session, scope, codes, group_ids, force)
    if not plan["todo"]:
        return {"started": True, "total": 0, "skipped": plan["skipped"], "reason": "全部已扫描"}

    threading.Thread(
        target=_run_scan, args=(plan["todo"], plan["name_map"], settings, today, scope), daemon=True
    ).start()
    return {"started": True, "total": plan["total"], "pending": True}
