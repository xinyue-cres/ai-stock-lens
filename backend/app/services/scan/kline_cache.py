"""K 线缓存读取与新鲜度判定：扫描时决定"直接用缓存 / 补拉 / 网络直拉"。"""
from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import text
from sqlmodel import Session, select

from app.db import engine
from app.models.kline import KlineDaily
from app.services.trader_service import _trading_days_between


def _parse_as_of(value) -> date | None:
    """把 trade_date（可能是 date/str/Timestamp）规整成 date。"""
    if isinstance(value, date):
        return value
    try:
        return pd.to_datetime(value).date()
    except Exception:  # noqa: BLE001
        return None


def _load_cached_kline(session: Session, code: str, start: date, min_bars: int = 1000) -> object | None:
    """从 KlineDaily 读 K 线缓存（已并入 analysis_service.load_kline_df 的 pd.read_sql 快路径）。

    保留旧签名兼容 scan/runner 与 scripts/（migrate_score_components.py /
    compare_daily_vs_weekly.py）的调用；`min_bars` 决定"覆盖不够 → None 走网络"的行为。

    覆盖扫描窗口（≥ min_bars × 0.9，容忍自然日/交易日换算误差）直接返回，否则 None。
    次新股兜底：库内根数不足 min_bars 但数据已是最新（>= 上一交易日）且够打分下限
    （score_stock 需 60 根）时直接返回现有数据——数据源全量也就这么多，走网络只会
    每次白拉一遍（002155 湖南黄金 290 根死循环实录）。
    """
    from app.services.analysis_service import load_kline_df

    df = load_kline_df(session, code, start=start, min_bars=int(min_bars * 0.9))
    if not df.empty:
        return df
    # 次新兜底：拉全量看实际有多少（不经 min_bars 截断）
    full = load_kline_df(session, code, start=start)
    if full.empty or len(full) < 60:
        return None  # 连打分下限都不够，只能走网络
    end = date.today()
    from datetime import datetime, time as dtime
    from zoneinfo import ZoneInfo
    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    # 盘中允许止于上一交易日；收盘后要求已到最近交易日（当日或上一交易日，
    # 与 _cache_needs_pull 的 grace=0 个股口径对齐）
    grace = 1 if (end == now.date() and now.time() < dtime(15, 0)) else 0
    if _trading_days_between(full["trade_date"].iloc[-1], end) > grace:
        return None  # 数据落后 → 走网络补拉（能拉到新的）
    # 数据已最新但根数天然不足 → 直接用，别再拉
    return full


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
    - grace=2（ETF：港股通/慢源数据源天然晚 1-2 天）：滞后 ≤2 个交易日仍视为最新 → 不补拉。
    latest 为 None（库无该股）时视为需补拉。
    """
    if latest is None:
        return True
    return _trading_days_between(latest, today) > grace


def _is_intraday_now(today: date) -> bool:
    """当前是否处于盘中（与 sync_service._is_intraday 同口径：今日 + 北京时间 < 15:00）。"""
    from datetime import datetime, time
    from zoneinfo import ZoneInfo

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    return today == now.date() and now.time() < time(15, 0)


def _cache_needs_pull(df: object | None, today: date, grace: int = 0,
                      intraday_relax: bool = False) -> bool:
    """缓存窗口是否需要补拉：无数据或 K 线落后到今天超过 grace（沿用 _is_stale）。

    仅做判定（不执行任何网络/写库），把"是否要补拉"交给调用方并发处理。
    grace 透传给 _is_stale：ETF 传 2（允许滞后 2 个交易日——港股通/慢源 ETF
    数据源天然晚 1-2 天，反复补拉也拿不到更新的，等于每次白拉），个股传 0。
    intraday_relax：当前时刻未到收盘（15:00 前）时，对个股额外 +1 天宽限——
    盘中扫描时"昨天收盘"就应该视为最新（今天的 bar 根本还不存在，
    数据源强拉也只返回昨收，照样不更新），否则全候选池都被错判 stale。
    """
    if df is None or df.empty:
        return True
    eff_grace = grace + (1 if intraday_relax else 0)
    return _is_stale(df["trade_date"].iloc[-1], today, eff_grace)
