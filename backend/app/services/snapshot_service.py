"""打分快照维护：同步 K 线后刷新 StockScore 行情字段 + 补算缺失 turnover。

从 sync_service 切分（sync 专注拉数据入库，快照维护独立）。
两个函数都被 sync_one_stock 在 K 线落库后调用。
"""
from __future__ import annotations

import logging
import math

from sqlmodel import Session, select

from app.models.kline import KlineDaily
from app.models.stock_score import StockScore

logger = logging.getLogger(__name__)


def _safe_float(v) -> float | None:
    """NaN/Inf/None → None，其余转 float。sync_service 也复用此工具。"""
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def refresh_score_snapshot(session: Session, code: str) -> None:
    """用 K 线库最新行刷新打分快照行情字段（当日波动/收盘/换手）。

    排行页 pct_chg 来自 StockScore 快照，而扫描时 as_of 常停在前一天（扫描在同步前）。
    同步后即使 K 线已最新（start>end 无新数据可拉），快照也须追上 K 线库，故这里
    查 K 线库最新行刷新。评分字段（total_score/各维度分）不动，那需要重扫。

    注意：as_of_date 不在此刷新——它的语义是"打分所用 K 线的截止日"，必须与
    components_json 同生同死。之前把它一起刷成最新，会掩盖"评分还停在旧数据"的事实，
    更致命的是扫描计划的自愈判断（runner: db_latest > snap_asof 则重算）读的就是它，
    被刷平后重算永远不触发，盘中旧打分从此无法被收盘新数据覆盖（2026-08-24 实录）。
    """
    latest_row = session.exec(
        select(KlineDaily).where(KlineDaily.code == code)
        .order_by(KlineDaily.trade_date.desc()).limit(1)
    ).first()
    if latest_row is None:
        return
    # 复合主键 (code, scan_timeframe)：刷新所有周期的快照（daily/weekly 都更新最新行情）
    scores = list(session.exec(
        select(StockScore).where(StockScore.code == code)
    ).all())
    if not scores:
        return
    new_close = float(latest_row.close) if latest_row.close is not None else None

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

    new_pct_chg = round(pct_chg, 2) if pct_chg is not None else None
    new_turnover = _safe_float(latest_row.turnover)
    for score in scores:
        score.close = new_close
        score.pct_chg = new_pct_chg
        score.turnover = new_turnover
        session.add(score)
    session.commit()


def fill_missing_turnover(session: Session, code: str) -> None:
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
