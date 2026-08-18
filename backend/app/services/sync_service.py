"""同步服务：拉取 K 线并入库。"""
from __future__ import annotations

import logging
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Session, delete, select

from app.datasource.router import get_data_router
from app.db import engine
from app.models.kline import KlineDaily
from app.models.stock import Stock
from app.models.sync_log import SyncLog

# 并发同步 worker 数（瓶颈是网络拉取；SQLite 已配 WAL + busy_timeout=30s 容忍并发写）
# 实测（8-18 自选 50 只）：16 是甜点（19s / 380ms/只）、12 紧随其后（21s / 422ms/只），
# 8 被东财频繁 cooldown 反而最慢（242s），20+ 触发 eastmoney rate limit fallback baostock 串行
_SYNC_WORKERS = 12

# 全量同步实时进度（前端弹窗轮询用；进程级单实例，用锁保护）
_sync_lock = threading.Lock()
_sync_progress: dict = {
    "running": False, "total": 0, "done": 0, "failed": 0,
    "current": None, "errors": [], "started_at": None, "finished_at": None,
}


def get_sync_progress() -> dict:
    """当前全量同步进度快照（/api/sync/status 透传）。"""
    with _sync_lock:
        return dict(_sync_progress)

logger = logging.getLogger(__name__)

_CN_TZ = ZoneInfo("Asia/Shanghai")
_MARKET_CLOSE = time(15, 0)

_last_indices_sync: datetime | None = None
_INDICES_COOLDOWN = timedelta(minutes=5)


def _now_cn() -> datetime:
    return datetime.now(_CN_TZ)


def _is_intraday(target: date) -> bool:
    """target 是"今天"且当前时间未到 15:00 → 正处于盘中/尚未收盘。"""
    now = _now_cn()
    return target == now.date() and now.time() < _MARKET_CLOSE


def _validate_row(row: dict, code: str) -> bool:
    """入库前一致性校验：拒绝明显异常的 K 线。

    规则：
    - close/open/high/low > 0
    - volume > 0
    - amount 与 close*volume 的偏差 < 30%（新浪的 amount 是 close*volume 估算的，容差要放宽）
    - high >= low, high >= open, high >= close
    异常返回 False，会被 sync 层丢弃并 log 告警。
    """
    try:
        close = float(row["close"])
        openp = float(row["open"])
        high = float(row["high"])
        low = float(row["low"])
        volume = float(row["volume"])
        amount = float(row["amount"])
    except (TypeError, ValueError, KeyError):
        return False
    # NaN 检查必须先做：NaN 与任何数字比较都返回 False，会绕过 <=0 判断
    if math.isnan(close) or math.isnan(volume) or math.isnan(amount):
        logger.warning("[%s %s] 字段含 NaN (疑似停牌行) 丢弃 close=%s vol=%s amt=%s",
                       code, row.get("trade_date"), close, volume, amount)
        return False
    if close <= 0 or volume <= 0 or amount <= 0:
        return False
    if not (high >= low and high >= openp and high >= close and low <= openp and low <= close):
        logger.warning("[%s %s] 价格 OHLC 不自洽 O=%s H=%s L=%s C=%s",
                       code, row.get("trade_date"), openp, high, low, close)
        return False
    if amount > 0 and volume > 0:
        expected = close * volume
        if expected > 0:
            ratio = amount / expected
            # 各源成交量单位不一：新浪/baostock=股（amount≈close×volume，即 ratio≈1），
            # 东财/腾讯=手（100 股，amount≈close×volume×100，即 ratio≈100）。
            # 命中任一量级即视为一致，都不中才判为脏数据——避免东财数据被整批误拒。
            if not (0.3 < ratio < 3) and not (30 < ratio < 300):
                logger.warning(
                    "[%s %s] 量额不一致：volume=%.0f amount=%.2f close=%.2f ratio=%.1f",
                    code, row.get("trade_date"), volume, amount, close, ratio,
                )
                return False
    return True


def _safe_float(v) -> float | None:
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _latest_date_in_db(session: Session, code: str) -> date | None:
    stmt = (
        select(KlineDaily.trade_date)
        .where(KlineDaily.code == code)
        .order_by(KlineDaily.trade_date.desc())
        .limit(1)
    )
    return session.exec(stmt).first()


def sync_one_stock(session: Session, code: str, full: bool = False) -> int:
    """同步单只股票的日线数据，返回新增/更新行数。"""
    router = get_data_router()

    end = date.today()
    if full:
        start = end - timedelta(days=365 * 5)
    else:
        latest = _latest_date_in_db(session, code)
        if latest:
            # 增量拉取多带 2 天窗口：sina/etf/指数 的 pct_chg = close.pct_change() 需要
            # 上一天 close 作基准。只拉 1 根时 pct_change 是 NaN 被 fillna(0) → 显示 0%。
            # 加 2 天后 df ≥3 根，pct_change 能算对；多余行用 session.merge 幂等更新，不重复入库。
            start = latest - timedelta(days=2)
        else:
            start = end - timedelta(days=365 * 5)
        # 若最近一次入库的日期就是今天，且当前仍在盘中：那条数据可能是盘中脏快照，
        # 强制回退一天并删除今日行，以便本次同步能重新拉当天的最新值。
        if latest == end and _is_intraday(end):
            logger.info("[%s] 盘中重拉当天：删除 %s 已有行", code, end)
            session.exec(delete(KlineDaily).where(KlineDaily.code == code, KlineDaily.trade_date == end))
            session.commit()
            start = end - timedelta(days=1)

    if start > end:
        # K 线已最新（无新数据可拉）：快照仍可能落后，用库最新行刷新
        _refresh_score_snapshot(session, code)
        return 0

    df = router.fetch_stock_daily(code, start, end)

    # 全量拉失败时降级到 2 年
    if (df is None or df.empty) and (end - start).days > 365 * 2:
        logger.warning("[%s] 全量 5 年拉取为空，降级到 2 年", code)
        start = end - timedelta(days=365 * 2)
        df = router.fetch_stock_daily(code, start, end)
    if df is None or df.empty:
        logger.warning("[%s] 同步无 K 线：数据源全部不可用或无该代码行情（%s~%s）", code, start, end)
        _refresh_score_snapshot(session, code)
        return 0

    inserted = 0
    rejected = 0
    for _, row in df.iterrows():
        trade_date_raw = row["trade_date"]
        if isinstance(trade_date_raw, str):
            trade_date = datetime.strptime(trade_date_raw, "%Y-%m-%d").date()
        else:
            trade_date = trade_date_raw

        row_dict = {
            "trade_date": trade_date,
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
            "amount": row["amount"],
        }
        if not _validate_row(row_dict, code):
            rejected += 1
            continue

        kline = KlineDaily(
            code=code,
            trade_date=trade_date,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row["volume"]) if not math.isnan(float(row["volume"])) else 0,
            amount=float(row["amount"]),
            turnover=_safe_float(row.get("turnover")),
            pct_chg=_safe_float(row.get("pct_chg")),
        )
        session.merge(kline)
        inserted += 1

    if rejected:
        logger.warning("[%s] 同步中丢弃 %d 行异常数据", code, rejected)
    session.commit()
    # 用 K 线库最新行（此时已含本次新拉数据）刷新打分快照行情字段
    _refresh_score_snapshot(session, code)
    # 注意：analysis_service 缓存指纹是最近 5 行内容 hash，K 线一改自动失效，无需手动 invalidate

    # 补算缺失的 turnover：从历史记录反推流通股本
    _fill_missing_turnover(session, code)
    return inserted


def _refresh_score_snapshot(session: Session, code: str) -> None:
    """用 K 线库最新行刷新打分快照行情字段（当日波动/收盘/换手/as_of_date）。

    排行页 pct_chg 来自 StockScore 快照，而扫描时 as_of 常停在前一天（扫描在同步前）。
    同步后即使 K 线已最新（start>end 无新数据可拉），快照也须追上 K 线库，故这里
    查 K 线库最新行刷新。评分字段（total_score/各维度分）不动，那需要重扫。
    """
    from app.models.stock_score import StockScore

    latest_row = session.exec(
        select(KlineDaily).where(KlineDaily.code == code)
        .order_by(KlineDaily.trade_date.desc()).limit(1)
    ).first()
    if latest_row is None:
        return
    score = session.get(StockScore, code)
    if score is None:
        return
    score.close = float(latest_row.close) if latest_row.close is not None else None

    # 若 pct_chg 为 None 或异常 0（常见：sina/etf/指数 增量拉只含 1 根，pct_change NaN 被 fillna(0)），
    # 用 K 线库前一天 close 反算真实涨跌幅——不覆盖合法 0%（两端 close 真相同则 pct_chg 也保持 0）。
    pct_chg = _safe_float(latest_row.pct_chg)
    if pct_chg is None or pct_chg == 0:
        prev_close = session.exec(
            select(KlineDaily.close)
            .where(KlineDaily.code == code, KlineDaily.trade_date < latest_row.trade_date)
            .order_by(KlineDaily.trade_date.desc()).limit(1)
        ).first()
        if prev_close and prev_close > 0 and latest_row.close:
            true_pct = (float(latest_row.close) / float(prev_close) - 1) * 100
            if abs(true_pct) > 0.0001:  # 真涨/真跌才覆盖
                pct_chg = true_pct

    score.pct_chg = round(pct_chg, 2) if pct_chg is not None else None
    score.turnover = _safe_float(latest_row.turnover)
    score.as_of_date = latest_row.trade_date
    session.add(score)
    session.commit()


def _fill_missing_turnover(session: Session, code: str) -> None:
    """从同只票最近有 turnover 的记录反推流通股本，补填 turnover=NULL 的行。"""
    ref = session.exec(
        select(KlineDaily)
        .where(KlineDaily.code == code, KlineDaily.turnover.isnot(None), KlineDaily.turnover > 0, KlineDaily.volume > 0)
        .order_by(KlineDaily.trade_date.desc())
        .limit(1)
    ).first()
    if not ref:
        return
    float_shares = ref.volume / (ref.turnover / 100)
    if float_shares <= 0:
        return

    missing = session.exec(
        select(KlineDaily)
        .where(KlineDaily.code == code, KlineDaily.turnover.is_(None), KlineDaily.volume > 0)
    ).all()
    if not missing:
        return

    for row in missing:
        row.turnover = round(row.volume / float_shares * 100, 4)
        session.add(row)
    session.commit()
    logger.info("[%s] 补算 %d 行缺失 turnover（流通股本推算 %.0f）", code, len(missing), float_shares)


def _sync_indices_if_due(session: Session) -> None:
    """带 5 分钟冷却的大盘指数同步。"""
    global _last_indices_sync
    now = datetime.now()
    if _last_indices_sync and (now - _last_indices_sync) < _INDICES_COOLDOWN:
        return
    try:
        from app.services.market_service import sync_indices
        sync_indices(session, days=30)
        _last_indices_sync = now
    except Exception:  # noqa: BLE001
        logger.exception("同步大盘指数失败（不影响自选股同步）")


def _sync_one_isolated(code: str) -> tuple[str, int, str | None]:
    """并发同步单只：每个 worker 用独立 session（主 session 不能跨线程共享）。

    异常时 with 上下文自动 rollback；已 commit 的部分保留。返回 (code, 插入行数, 错误消息|None)。
    """
    from sqlmodel import Session as S

    try:
        with S(engine) as s:
            inserted = sync_one_stock(s, code)
            return code, inserted, None
    except Exception as e:  # noqa: BLE001
        logger.exception("同步 %s 失败", code)
        return code, 0, str(e)


def sync_watchlist(session: Session) -> SyncLog:
    log = SyncLog(started_at=datetime.now(), status="running")
    session.add(log)
    session.commit()
    session.refresh(log)

    # 初始化实时进度（前端弹窗轮询）
    with _sync_lock:
        _sync_progress.update(
            running=True, total=0, done=0, failed=0,
            current=None, errors=[], started_at=datetime.now(), finished_at=None,
        )

    # 先同步大盘指数（供 AI 分析和大盘状态条使用），带冷却
    _sync_indices_if_due(session)

    stocks = list(session.exec(select(Stock).where(Stock.is_watchlist == True)))  # noqa: E712
    codes = [s.code for s in stocks]
    with _sync_lock:
        _sync_progress["total"] = len(codes)
    total = 0
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=_SYNC_WORKERS) as pool:
        for code, inserted, err in pool.map(_sync_one_isolated, codes):
            with _sync_lock:
                _sync_progress["done"] += 1
                _sync_progress["current"] = code
            if err:
                errors.append(f"{code}: {err}")
                with _sync_lock:
                    _sync_progress["failed"] += 1
                    if len(_sync_progress["errors"]) < 20:
                        _sync_progress["errors"].append(f"{code}: {err[:150]}")
            else:
                total += inserted

    with _sync_lock:
        _sync_progress.update(running=False, finished_at=datetime.now())
    log.finished_at = datetime.now()
    log.stocks_synced = len(stocks) - len(errors)
    log.status = "success" if not errors else ("failed" if len(errors) == len(stocks) else "partial")
    log.error_msg = "\n".join(errors) if errors else None
    session.add(log)
    session.commit()
    session.refresh(log)
    logger.info(
        "同步完成 status=%s success=%d/%d rows=%d (并发%d)",
        log.status, log.stocks_synced, len(stocks), total, _SYNC_WORKERS,
    )
    return log, total, len(stocks)
