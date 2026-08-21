"""选股扫描编排：候选池 → 拉 K 线 → 打分 + 趋势判断 → upsert StockScore。

关键设计：
- 扫描优先用库内 K 线缓存（串行读），覆盖 ≥ ~1000 根窗口才命中；
  缓存命中但落后到今天（≥1 交易日）→ 统一「并发增量补拉」缺的最近几根
  （复用 sync_service 的工作台并发单只 worker _sync_one_isolated），不重拉全量；
  缓存不足/补拉后仍不足才网络直拉。
- 打分基于"今日收盘已入库"的最新 K 线；当日已扫但 K 线库又新增收盘线 → 自动重算。
- 网络/补拉全程 ThreadPoolExecutor 并发 + 每请求 sleep 限流，防数据源封禁。
- 全局 _scan_state 供前端轮询进度；进程级锁保证单扫描实例；支持取消。
- 每个补拉 worker 用独立的 SQLAlchemy Session（Session 不是线程安全的）。
"""
from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import text
from sqlmodel import Session, select

from app.config import get_settings
from app.datasource.base_provider import is_fund_code
from app.datasource.router import get_data_router
from app.db import engine
from app.features.stock_scorer import compute_indicator_cache, score_stock
from app.features.timeframe import Timeframe, to_bars
from app.features.trend_judge import judge_trend
from app.models.kline import KlineDaily
from app.models.stock import Stock
from app.models.stock_score import StockScore
from app.services.dividend_service import load_dividend_map
from app.services.stock_service import watchlist_codes_in_groups
from app.services.sync_service import _sync_one_isolated
from app.services.trader_service import _trading_days_between

logger = logging.getLogger(__name__)

# ETF/LOF 的缓存门槛：基金历史短、次新多，且 ETF 数据源常晚一天/不足 900 根；
# 放宽到 ≥300 根即可打分（score_stock/_MIN_ROWS=60），避免不足 900 根就走网络拉取→失败→不显示。
_ETF_MIN_BARS = 300


def _min_bars_for(code: str, settings) -> int:
    """打分窗口所需的缓存根数：ETF 放宽（_ETF_MIN_BARS），个股用扫描配置(默认 1000)。"""
    return _ETF_MIN_BARS if is_fund_code(code) else settings.scan_kline_bars


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


def _load_cached_kline(session: Session, code: str, start: date, min_bars: int = 1000) -> object | None:
    """从 KlineDaily 读 K 线缓存。

    覆盖扫描窗口（≥ min_bars × 0.9，容忍自然日/交易日换算误差）直接返回，否则 None 走网络拉取。
    用 pandas.read_sql 直连读（比 SQLModel ORM 逐行构造对象快 ~5 倍，扫描 1000+ 只时节省数秒）。
    session 参数仅用于保持一致签名（真实查询走 engine 连接池）。
    """
    sql = text("""
        SELECT trade_date, open, high, low, close, volume, amount, turnover, pct_chg
        FROM kline_daily
        WHERE code = :code AND trade_date >= :start
        ORDER BY trade_date ASC
    """)
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"code": code, "start": start})
    if len(df) < int(min_bars * 0.9):
        return None
    # read_sql 把 date 列读成 str；转回 date 以保持与 ORM 版一致（下游 _is_stale/排序/快照都用真日期）
    if len(df) and not isinstance(df["trade_date"].iloc[0], date):
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df


def _latest_db_dates(session: Session, codes: list[str]) -> dict[str, date | None]:
    """批量查询候选股票在 K 线库中的最后交易日（code → date|None）。

    ∥ 供扫描计划判断"库里是否已有更新的收盘线"（避免 N+1 逐票查）。
    """
    if not codes:
        return {}
    rows = session.exec(
        select(KlineDaily.code, KlineDaily.trade_date)
        .where(KlineDaily.code.in_(codes))  # type: ignore[attr-defined]
        .order_by(KlineDaily.trade_date.asc())
    ).all()
    out: dict[str, date | None] = {c: None for c in codes}
    for code, d in rows:
        out[code] = d  # 升序遍历，最后一次赋值即该票最新日期
    return out


def _is_stale(latest: date | None, today: date, grace: int = 0) -> bool:
    """K 线是否落后到今天超过 grace 个交易日（沿用 _trading_days_between：跳周末、不算节假日）。

    - 周五收盘数据在周六/周日不判落后；周一开盘后再扫描才会触发补拉。
    - grace=0（个股）：落后今天 ≥1 交易日即算旧 → 需补拉。
    - grace=1（ETF：数据源天然晚一天）：允许滞后再 1 个交易日，昨日数据仍视为最新 → 不补拉。
    latest 为 None（库无该股）时视为需补拉。
    """
    if latest is None:
        return True
    return _trading_days_between(latest, today) > grace


def _cache_needs_pull(df: object | None, today: date, grace: int = 0) -> bool:
    """缓存窗口是否需要补拉：无数据或 K 线落后到今天超过 grace（沿用 _is_stale）。

    仅做判定（不执行任何网络/写库），把"是否要补拉"交给调用方并发处理。
    grace 透传给 _is_stale：ETF 传 1（允许昨日），个股传 0。
    """
    if df is None or df.empty:
        return True
    return _is_stale(df["trade_date"].iloc[-1], today, grace)


def _upsert(session: Session, code: str, name: str, scored: dict, trend: dict,
            scan_date: date, as_of_date: date | None, scope: str,
            timeframe: Timeframe = "daily") -> None:
    # 复合主键 (code, scan_timeframe)：daily/weekly 各占一行，互不覆盖
    row = session.get(StockScore, (code, timeframe))
    if row is None:
        row = StockScore(code=code, scan_timeframe=timeframe)
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
                    if _cache_needs_pull(df, end, grace=1 if is_fund_code(code) else 0):
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
                        trend = judge_trend(bars, signal_score=scored["signal_score"], cache=cache)
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
