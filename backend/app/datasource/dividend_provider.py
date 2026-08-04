"""股息/分红数据获取。

策略：优先按年度拉全市场分红表（`ak.stock_fhps_em`，一年一次调用拿全市场），
聚合出每只股票近 3 年平均股息率；单股缺失时降级到 `ak.stock_fhps_detail_em`。
ETF/LOF 无分红表，返回 None（打分给中性分）。结果缓存进 StockDividend 表，30 天刷新。

注意：akshare 接口签名易变，这里对每个接口都做了 try/except 降级，
任何一步失败都回退为 None，不阻塞主扫描流程。
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import pandas as pd

from app.datasource.base_provider import is_fund_code
from app.models.stock_dividend import StockDividend

logger = logging.getLogger(__name__)

_CACHE_DAYS = 30
_YEARS = 3  # 近 3 个年度平均
_FULL_TABLE_THRESHOLD = 100  # 候选数达到该值才拉全市场年度分红表；否则逐只单股接口


def _recent_year_ends() -> list[str]:
    """近 N 个完整年度的 'YYYY1231' 报告期参数。"""
    today = date.today()
    year = today.year
    if today.month < 3:
        year -= 1  # 年初时上一年度分红可能尚未实施完
    return [f"{year - i}1231" for i in range(_YEARS)]


def _fetch_year_table(ak, year_end: str) -> dict[str, list[float]]:
    """拉单个年度的全市场分红表，返回 {code: [该年度股息率...]}（小数）。"""
    df = ak.stock_fhps_em(date=year_end)
    if df is None or df.empty or "代码" not in df.columns or "现金分红-股息率" not in df.columns:
        return {}
    result: dict[str, list[float]] = {}
    for _, row in df.iterrows():
        code = str(row["代码"])
        y = row.get("现金分红-股息率")
        if pd.notna(y):
            try:
                v = float(y)
            except (TypeError, ValueError):
                continue
            if v > 0:
                result.setdefault(code, []).append(v)
    return result


def _fetch_single(ak, code: str) -> list[float]:
    """单股分红详情，返回近 _YEARS 条有效股息率。"""
    df = ak.stock_fhps_detail_em(symbol=code)
    if df is None or df.empty or "现金分红-股息率" not in df.columns:
        return []
    yields_ = []
    for _, row in df.iterrows():
        y = row.get("现金分红-股息率")
        if pd.notna(y):
            try:
                v = float(y)
            except (TypeError, ValueError):
                continue
            if v > 0:
                yields_.append(v)
    return yields_[:_YEARS]


def _aggregate(yields_list: list[float]) -> float | None:
    """平均股息率，统一转成百分数（如 3.2 = 3.2%）。"""
    if not yields_list:
        return None
    return round(sum(yields_list) / len(yields_list) * 100, 2)


def _fetch_yields_batch(codes: list[str]) -> dict[str, float | None]:
    """批量拉取股息率。

    - 候选数多（>= _FULL_TABLE_THRESHOLD，如全市场扫描）：拉全市场年度分红表，一次覆盖全部；
    - 候选数少（自选/分组扫描）：逐只单股接口，避免为几只股票拉全市场大表（慢 + 缓存膨胀）。
    全表没覆盖到的缺失股票始终用单股接口补。
    """
    from app.datasource.akshare_guard import get_ak

    ak = get_ak()

    per_code: dict[str, list[float]] = {}
    if len(codes) >= _FULL_TABLE_THRESHOLD:
        for year_end in _recent_year_ends():
            try:
                table = _fetch_year_table(ak, year_end)
                for code in codes:
                    if code in table:
                        per_code.setdefault(code, []).extend(table[code])
            except Exception:  # noqa: BLE001
                logger.warning("拉取 %s 年度分红表失败，跳过", year_end)

    # 小列表直接走单股接口；全表没覆盖到的也用单股接口补
    missing = [c for c in codes if c not in per_code]
    for code in missing:
        try:
            yields_ = _fetch_single(ak, code)
            if yields_:
                per_code[code] = yields_
        except Exception:  # noqa: BLE001
            logger.debug("单股分红 %s 拉取失败", code)

    return {code: _aggregate(per_code.get(code, [])) for code in codes}


def _save(session, code: str, avg_yield: float | None) -> None:
    row = session.get(StockDividend, code)
    if row is None:
        row = StockDividend(code=code)
    row.avg_yield_3y = avg_yield
    row.years = _YEARS if avg_yield is not None else 0
    row.updated_at = date.today()
    session.add(row)


def load_dividend_map(session, codes: list[str]) -> dict[str, float | None]:
    """批量取近 3 年平均股息率 map：{code: 股息率(%) | None}。

    优先读 StockDividend 缓存（30 天内），缺失/过期的批量拉取并写回。
    ETF/LOF 直接返回 None（无分红表）。
    """
    if not codes:
        return {}
    stock_codes = [c for c in codes if not is_fund_code(c)]
    if not stock_codes:
        return {}

    result: dict[str, float | None] = {}
    stale: list[str] = []
    today = date.today()
    for code in stock_codes:
        row = session.get(StockDividend, code)
        if row and row.avg_yield_3y is not None and (today - row.updated_at).days < _CACHE_DAYS:
            result[code] = row.avg_yield_3y
        else:
            stale.append(code)

    if stale:
        fresh = _fetch_yields_batch(stale)
        for code, y in fresh.items():
            result[code] = y
            _save(session, code, y)
        try:
            session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("写入股息缓存失败")
            session.rollback()

    return result


def get_dividend_yield(session, code: str) -> float | None:
    """单只查询（薄封装 load_dividend_map）。"""
    return load_dividend_map(session, [code]).get(code)


def purge_dividend_cache(session, days: int = _CACHE_DAYS) -> int:
    """清理超过 days 天未刷新的缓存行，返回清理条数。供扫描前主动刷新用。"""
    cutoff = date.today() - timedelta(days=days)
    from sqlmodel import select

    rows = session.exec(select(StockDividend).where(StockDividend.updated_at < cutoff)).all()
    for row in rows:
        session.delete(row)
    session.commit()
    return len(rows)
