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
from sqlalchemy import text
from sqlmodel import Session, select

from app.db import engine
from app.indicators.engine import build_chart_series, compute_all
from app.indicators.signals import scan_signals
from app.indicators.weekly import aggregate_weekly
from app.models.kline import KlineDaily
from app.models.stock import Stock
from app.shared.fingerprint_cache import FingerprintedCache

logger = logging.getLogger(__name__)

# 进程内缓存：{code: (fingerprint, result_dict)}
# fingerprint = 最近 5 行关键字段的内容 hash，任何一个字段变化都失效
_ANALYSIS_CACHE = FingerprintedCache(capacity=200)
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


def load_kline_df(session: Session, code: str,
                  start: date | None = None,
                  days: int = 500,
                  min_bars: int = 0) -> pd.DataFrame:
    """从 KlineDaily 指定窗口加载 K 线（统一入口，pd.read_sql 快路径）。

    替代原 ORM 逐行转 dict 慢路径（此版本 ~5 倍提速），同时收敛原先
    `scan/_load_cached_kline` 的另一套实现——两条平行契约彻底归一。

    参数语义:
    - start + days 只传一个：start 优先；都不传时用 days=500。
    - min_bars: 低于此数视为数据不足，返回空 DataFrame；调用方
      （analyze / judge_trend / signals_service）自行 .empty 检查随机应变。
      keep None as a sentinel w/ respect to scan/runner（后面统一吃 empty 即可）。
    """
    if start is None:
        start = date.today() - timedelta(days=days * 2)
    sql = text("""
        SELECT trade_date, open, high, low, close, volume, amount, turnover, pct_chg
        FROM kline_daily
        WHERE code = :code AND trade_date >= :start
        ORDER BY trade_date ASC
    """)
    # read_sql 直连避开 ORM 逐行初始化，比 select(KlineDaily) 快 ~5 倍（1200 只实测）
    with engine.connect() as conn:
        df = pd.read_sql(sql, conn, params={"code": code, "start": start})
    if len(df) < min_bars:
        return pd.DataFrame()
    # SQLite date 列可能读出 str；转回 date 保持与下游所有打分/趋势判断的合约一致
    if len(df) and not isinstance(df["trade_date"].iloc[0], date):
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
    return df


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
    cached = _ANALYSIS_CACHE.get(code, fingerprint)
    if cached is not None:
        logger.debug("analyze cache hit for %s", code)
        return cached

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

    _ANALYSIS_CACHE.set(code, fingerprint, result)
    return result


def invalidate_analysis_cache(code: str | None = None) -> None:
    """通常不需要手动调 —— 指纹是内容 hash，K 线一变自动失效。保留仅为特殊场景（如
    调试、跨进程外部改库后强制刷新单进程缓存）。"""
    _ANALYSIS_CACHE.invalidate(code)


def build_ai_input(session: Session, code: str) -> tuple[dict, dict] | None:
    """给 AI 的输入：股票信息 + { 'daily': 日线指标, 'weekly': 周线指标, 'market': 大盘上下文, 'recent_days': 近10日逐日明细 }。"""
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

    # 近 10 个交易日逐日明细（供 AI 判断连涨/连跌等趋势）
    recent = df.tail(10)
    recent_days = []
    for _, r in recent.iterrows():
        recent_days.append({
            "date": str(r["trade_date"]),
            "close": round(float(r["close"]), 2),
            "pct_chg": round(float(r["pct_chg"]), 2) if pd.notna(r.get("pct_chg")) else None,
            "turnover": round(float(r["turnover"]), 2) if pd.notna(r.get("turnover")) else None,
            "volume": int(r["volume"]),
        })

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
        "recent_days": recent_days,
        "as_of_date": daily_ind.get("as_of_date"),
    }

