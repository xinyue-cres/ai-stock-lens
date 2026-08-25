"""扫描主流程：build_plan → run_scan（后台线程）→ scan_market（入口）。

从 state/pool/kline_cache/writer 四个模块取原料，只做编排，不做具体业务。
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from sqlmodel import Session, select

from app.config import get_settings
from app.datasource.base_provider import is_fund_code
from app.datasource.router import get_data_router
from app.db import engine
from app.features.scoring import compute_indicator_cache, score_stock
from app.features.timeframe import Timeframe, to_bars
from app.features.trend_judge import judge_trend
from app.models.stock_score import StockScore
from app.services.dividend_service import load_dividend_map
from app.services.sync_service import _sync_one_isolated

from .kline_cache import (
    _cache_needs_pull,
    _is_intraday_now,
    _latest_db_dates,
    _load_cached_kline,
    _parse_as_of,
)
from .pool import _build_pool, _min_bars_for
from .state import _scan_lock, _scan_state
from .writer import _upsert

logger = logging.getLogger(__name__)


def _build_plan(session: Session, scope: str, codes: list[str] | None,
                group_ids: list[int] | None, force: bool,
                timeframe: Timeframe = "daily") -> dict:
    """同步构建扫描计划：候选池 + 当日去重。

    去重口径按 (scan_date, scan_scope, scan_timeframe) 三元组：同一天 daily 扫过不跳过
    weekly 扫描，反之亦然——两个周期的打分互相独立（用户切换查看周期时不被另一种的
    存量记录"截胡"）。

    返回 {todo, name_map, total, skipped}；todo 为空（全部已扫描）时同时把
    running 置回 False。候选池构建失败会抛异常（调用方负责复位状态）。
    """
    today = date.today()
    try:
        candidates, name_map = _build_pool(session, scope, codes, group_ids)
        if not force:
            # 当日已扫的记录 → 快照 as_of_date（该次打分用到的 K 线最后交易日）
            # 多周期隔离：scope/timeframe 任一不匹配都不参与去重
            scanned: dict[str, date | None] = {
                r.code: r.as_of_date
                for r in session.exec(
                    select(StockScore.code, StockScore.as_of_date)
                    .where(StockScore.scan_date == today)
                    .where(StockScore.scan_timeframe == timeframe)
                    .where(StockScore.scan_scope == scope)
                ).all()
            }
            latest_dates = _latest_db_dates(session, list(scanned.keys()))
            todo: list[str] = []
            skipped = 0
            for c in candidates:
                if c in scanned:
                    db_latest = latest_dates.get(c)
                    snap_asof = scanned[c]
                    # 当日已扫但 K 线库出现了更新的收盘线（比打分时 as_of_date 更晚）→ 用今日收盘重算
                    if db_latest is not None and (snap_asof is None or db_latest > snap_asof):
                        todo.append(c)
                    else:
                        skipped += 1
                else:
                    todo.append(c)
        else:
            todo = list(candidates)
            skipped = 0

        with _scan_lock:
            _scan_state["total"] = len(todo)

        if not todo:
            with _scan_lock:
                _scan_state.update(running=False, finished_at=today.isoformat())

        return {"todo": todo, "name_map": name_map, "total": len(todo), "skipped": skipped}
    except Exception:  # noqa: BLE001
        with _scan_lock:
            _scan_state.update(running=False, finished_at=date.today().isoformat())
        raise


def _run_scan(todo: list[str], name_map: dict[str, str], settings, today: date, scope: str,
              timeframe: Timeframe = "daily") -> None:
    """后台线程执行实际打分（启动后立即返回，不阻塞 POST）。

    关键性能设计（数据同步后缓存充足，SQLite 并发读成为瓶颈）：
    1. 单 Session 串行读缓存——SQLite WAL 多连接并发读竞争严重（实测 12 并发慢 8.7 倍），
       必须先单连接把所有 K 线缓存读出来（快），未命中的才走网络；
    2. 缓存未命中 → 并发网络拉取（网络 I/O 释放 GIL，并发有收益）；
    3. compute + upsert 串行（GIL 下并发计算无收益，串行最简最快）。

    股息 map 在后台线程内用独立 Session 拉取：请求级 session 已随 POST 返回被关闭，
    不能复用（复用会抛异常→扫描静默中断 done=0）。
    """
    try:
        try:
            with Session(engine) as div_s:
                dividend_map = load_dividend_map(div_s, todo)
        except Exception:  # noqa: BLE001
            logger.warning("预加载股息 map 失败，按无股息处理")
            dividend_map = {}

        # 1) 串行读缓存（快路径；数据同步后绝大多数走这里）
        #    只做判定：已最新→直接用；缓存够但落后→收集待补拉；不足900→待网络
        end = date.today()
        start = end - timedelta(days=settings.scan_kline_days)
        # 盘中扫描（15:00 前）：今天还没收盘，"昨天数据"应视为最新——加宽 grace+1
        # （否则全候选池被判 stale 触发网络补拉，但数据源最强的也只有昨收，等于白拉）
        intraday = _is_intraday_now(end)
        cache_map: dict[str, object] = {}
        need_net: list[str] = []
        pull_codes: list[str] = []
        try:
            with Session(engine) as s:
                for code in todo:
                    df = _load_cached_kline(s, code, start, min_bars=_min_bars_for(code, settings))
                    if df is None:
                        need_net.append(code)
                        continue
                    if _cache_needs_pull(df, end, grace=2 if is_fund_code(code) else 0,
                                         intraday_relax=intraday):
                        pull_codes.append(code)  # 收集，稍后统一并发补拉（不在此串行原地拉）
                    else:
                        cache_map[code] = df
        except Exception:  # noqa: BLE001
            logger.exception("读 K 线缓存失败，全部走网络")
            need_net = list(todo)

        # 1.5) 并发增量补拉（写回 kline_daily）——统一用工作台 sync_watchlist 那套
        #     _sync_one_isolated（每 worker 独立 Session），避免逐只串行等网络
        if pull_codes:
            with ThreadPoolExecutor(max_workers=settings.scan_concurrency) as pool:
                list(pool.map(_sync_one_isolated, pull_codes))
            # 补拉后重读缓存
            with Session(engine) as s:
                for code in pull_codes:
                    df = _load_cached_kline(s, code, start, min_bars=_min_bars_for(code, settings))
                    if df is not None:
                        cache_map[code] = df
                    else:
                        need_net.append(code)

        # 2) 仍未命中 → 并发网络拉取（网络 I/O 释放 GIL，并发提速）
        def _fetch_net(code: str) -> tuple[str, object | None]:
            if _scan_state["cancel_requested"]:
                return code, None
            try:
                df = get_data_router().fetch_stock_daily(code, start, end)
                time.sleep(0.02)  # 请求间限流，防数据源封禁
                return code, df
            except Exception:  # noqa: BLE001
                logger.warning("拉取 %s K 线失败", code)
                return code, None

        if need_net:
            with ThreadPoolExecutor(max_workers=settings.scan_concurrency) as pool:
                for code, df in pool.map(_fetch_net, need_net):
                    if df is not None and not df.empty:
                        cache_map[code] = df

        # 3) 串行 compute + upsert（GIL 下并发计算无收益，串行最简最快）
        for code in todo:
            if _scan_state["cancel_requested"]:
                break
            failed = True
            try:
                daily_df = cache_map.get(code)
                if daily_df is not None and not daily_df.empty:
                    # 周期转换：daily→原样；weekly→resample 到周五收盘 bar。
                    # scorer/judge 全是 bar-级运算，与底层 K 线粒度解耦（见 features/timeframe.py）
                    bars = to_bars(daily_df, timeframe)
                    # 指标只算一次，score_stock 与 judge_trend 复用（避免重复算 MACD/ADX/BOLL/Risk）
                    cache = compute_indicator_cache(bars)
                    scored = score_stock(bars, dividend_map.get(code), is_fund_code(code),
                                         cache=cache, timeframe=timeframe)
                    if scored is not None:
                        trend = judge_trend(bars, signal_score=scored["signal_score"],
                                            cache=cache, timeframe=timeframe)
                        as_of_date = _parse_as_of(bars["trade_date"].iloc[-1])
                        with Session(engine) as s:
                            _upsert(s, code, name_map.get(code, code), scored, trend,
                                    today, as_of_date, scope, timeframe=timeframe)
                        failed = False
            except Exception:  # noqa: BLE001
                logger.exception("打分失败 %s", code)
            with _scan_lock:
                _scan_state["done"] += 1
                if failed:
                    _scan_state["failed"] += 1
                _scan_state["current"] = code
    finally:
        with _scan_lock:
            _scan_state.update(running=False, finished_at=date.today().isoformat())


def scan_market(session: Session, scope: str = "all", codes: list[str] | None = None,
                force: bool = False, group_ids: list[int] | None = None,
                timeframe: Timeframe = "daily") -> dict:
    """触发一次全市场/自选股扫描。已在 running 时直接返回不重复启动。

    group_ids：scope=watchlist/group 时可传多个自选分组 id，只扫这些分组内的自选股（任意匹配）。
    timeframe：打分基于的 K 线周期（daily/weekly），仅影响 bar 重采样与 scan_timeframe 标记。

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
    plan = _build_plan(session, scope, codes, group_ids, force, timeframe=timeframe)
    if not plan["todo"]:
        return {"started": True, "total": 0, "skipped": plan["skipped"], "reason": "全部已扫描"}

    threading.Thread(
        target=_run_scan, args=(plan["todo"], plan["name_map"], settings, today, scope, timeframe),
        daemon=True,
    ).start()
    return {"started": True, "total": plan["total"], "pending": True}
