"""同步服务：拉取 K 线并入库。"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlmodel import Session, delete, select

from app.datasource.router import get_data_router
from app.models.kline import KlineDaily
from app.models.stock import Stock
from app.models.sync_log import SyncLog

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
            deviation = abs(amount / expected - 1)
            if deviation > 0.3:
                logger.warning(
                    "[%s %s] 量额不一致：volume=%.0f amount=%.2f close=%.2f 偏差 %.1f%%",
                    code, row.get("trade_date"), volume, amount, close, deviation * 100,
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
        start = (latest + timedelta(days=1)) if latest else end - timedelta(days=365 * 5)
        # 若最近一次入库的日期就是今天，且当前仍在盘中：那条数据可能是盘中脏快照，
        # 强制回退一天并删除今日行，以便本次同步能重新拉当天的最新值。
        if latest == end and _is_intraday(end):
            logger.info("[%s] 盘中重拉当天：删除 %s 已有行", code, end)
            session.exec(delete(KlineDaily).where(KlineDaily.code == code, KlineDaily.trade_date == end))
            session.commit()
            start = end

    if start > end:
        return 0

    df = router.fetch_stock_daily(code, start, end)

    # 全量拉失败时降级到 2 年
    if (df is None or df.empty) and (end - start).days > 365 * 2:
        logger.warning("[%s] 全量 5 年拉取为空，降级到 2 年", code)
        start = end - timedelta(days=365 * 2)
        df = router.fetch_stock_daily(code, start, end)
    if df is None or df.empty:
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
    # 注意：analysis_service 缓存指纹是最近 5 行内容 hash，K 线一改自动失效，无需手动 invalidate

    # 补算缺失的 turnover：从历史记录反推流通股本
    _fill_missing_turnover(session, code)
    return inserted


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


def sync_watchlist(session: Session) -> SyncLog:
    log = SyncLog(started_at=datetime.now(), status="running")
    session.add(log)
    session.commit()
    session.refresh(log)

    # 先同步大盘指数（供 AI 分析和大盘状态条使用），带冷却
    _sync_indices_if_due(session)

    stocks = list(session.exec(select(Stock).where(Stock.is_watchlist == True)))  # noqa: E712
    total = 0
    errors: list[str] = []
    for stock in stocks:
        # 提前抓出 code：session 若在 sync_one_stock 内 flush 失败会进入 pending-rollback，
        # 之后再读 stock.code 会触发 lazy load → PendingRollbackError 覆盖真实异常
        code = stock.code
        try:
            total += sync_one_stock(session, code)
        except Exception as e:  # noqa: BLE001
            logger.exception("同步 %s 失败", code)
            errors.append(f"{code}: {e}")
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass

    log.finished_at = datetime.now()
    log.stocks_synced = len(stocks) - len(errors)
    log.status = "success" if not errors else ("failed" if len(errors) == len(stocks) else "partial")
    log.error_msg = "\n".join(errors) if errors else None
    session.add(log)
    session.commit()
    session.refresh(log)
    logger.info(
        "同步完成 status=%s success=%d/%d rows=%d",
        log.status, log.stocks_synced, len(stocks), total,
    )
    return log, total, len(stocks)
