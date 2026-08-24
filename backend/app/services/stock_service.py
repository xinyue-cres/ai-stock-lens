"""股票元数据服务。"""
from __future__ import annotations

import json
import logging
import threading
from datetime import date, timedelta

from sqlmodel import Session, select

from app.datasource.base_provider import infer_market
from app.datasource.router import get_data_router
from app.models.stock import Stock

logger = logging.getLogger(__name__)

# 远程列表拉取互斥锁：lru_cache 不去重并发调用——联想栏连续请求会同时
# 进入 get_stock_list，各自拉一遍 10-30s 远程列表（缓存踩踏），
# 慢请求各自占住一个 DB 连接等网络，直接打爆 QueuePool（曾致 500）。
_remote_list_lock = threading.Lock()


def ensure_stock(session: Session, code: str) -> Stock:
    """从库中取或从数据源查一次并入库。

    匹配顺序：
    1. 库里已有 → 直接返回
    2. 全量列表（进程内缓存）匹配 → 拿到真实名称入库
    3. 列表接口失败 / 列表未收录该代码 → 用 K 线拉取验证代码有效性
       （数据源 fallback 链能拉到即视为有效），以推断市场建行（name 先用代码占位）
    避免依赖单一东财列表接口：列表挂了或新上市代码不在列表时，添加不再直接 500。
    """
    stock = session.get(Stock, code)
    if stock:
        return stock

    try:
        for info in get_data_router().get_stock_list():
            if info.code == code:
                stock = Stock(code=info.code, name=info.name, market=info.market)
                session.add(stock)
                session.commit()
                session.refresh(stock)
                return stock
    except Exception:  # noqa: BLE001
        # 列表接口失败（如东财不可用）不阻断添加，降级到 K 线验证
        logger.warning("[%s] 股票列表获取失败，降级为 K 线验证", code)

    df = get_data_router().fetch_stock_daily(
        code, date.today() - timedelta(days=30), date.today()
    )
    if df is not None and not df.empty:
        stock = Stock(code=code, name=code, market=infer_market(code))
        session.add(stock)
        session.commit()
        session.refresh(stock)
        return stock

    raise ValueError(f"股票代码 {code} 不存在或暂时无法获取行情")


def refresh_stock_index(session: Session) -> int:
    """从数据源拉全 A 股列表填充到 stock 表，返回新增数量。

    code 统一清洗为 6 位（sina/东财 ETF 源返回 "sh600519"/"sz159998" 带前缀格式，
    直接入库会与业务用的 6 位 code 形成两条独立记录）。
    """
    infos = get_data_router().get_stock_list()
    added = 0
    for info in infos:
        code = info.code[-6:]
        if len(code) != 6 or not code.isdigit():
            continue
        existing = session.get(Stock, code)
        if existing is None:
            session.add(Stock(code=code, name=info.name, market=info.market))
            added += 1
        elif existing.name != info.name:
            existing.name = info.name
            session.add(existing)
    session.commit()
    if added:
        logger.info("股票元数据补齐：新增 %d 条", added)
    return added


def _count_stocks(session: Session) -> int:
    from sqlalchemy import func

    return session.exec(select(func.count()).select_from(Stock)).one()


def search_stocks(session: Session, keyword: str, limit: int = 20) -> list[Stock]:
    if _count_stocks(session) < 100:
        try:
            refresh_stock_index(session)
        except Exception:
            logger.exception("补齐股票元数据失败")
    stmt = (
        select(Stock)
        .where((Stock.name.contains(keyword)) | (Stock.code.contains(keyword)))
        .limit(limit)
    )
    results = list(session.exec(stmt))
    if results:
        return results

    # 本地没找到。拉丁字母（拼音输入中间态 t/tia/tian'j）直接返回空：
    # A 股名是中文、代码是数字，拉丁字符必然无匹配，远程拉 10-30s
    # 纯浪费还会占满连接池（曾导致 QueuePool 耗尽 500）。
    if keyword.isascii() and not keyword.isdigit():
        return []

    # 远程列表搜索（覆盖 ETF/LOF 等本地未入库的品种）。
    # 注意清洗市场前缀：东财 ETF 列表返回 "sz159998" 这类带前缀 code，
    # 直接入库会与业务用的 6 位 code 形成两条独立记录（曾经污染过 42 行）。
    try:
        remote_matches = []
        with _remote_list_lock:  # 全 A 列表只拉一次：并发请求排队等第一个结果（lru_cache 命中后锁零成本）
            for s in get_data_router().get_stock_list():
                clean_code = s.code[-6:]
                if keyword in clean_code or keyword in (s.name or ""):
                    remote_matches.append((clean_code, s.name, s.market))
                if len(remote_matches) >= limit:
                    break
        for code, name, market in remote_matches:
            if not session.get(Stock, code):
                session.add(Stock(code=code, name=name, market=market))
        if remote_matches:
            session.commit()
        return [session.get(Stock, c) for c, _, _ in remote_matches if session.get(Stock, c)]
    except Exception:
        logger.exception("远程搜索失败")
        return []


def list_watchlist(session: Session) -> list[Stock]:
    return list(session.exec(select(Stock).where(Stock.is_watchlist == True)))  # noqa: E712


def watchlist_codes_in_groups(session: Session, group_ids: list[int] | None = None) -> set[str]:
    """自选股代码集合，可选按自选分组过滤（命中任一分组即算，任意匹配）。

    group_ids 为空/None 时返回全部自选代码。选股扫描候选池与打分列表的
    group_ids 过滤共用，避免各写一套"加载自选 + get_group_ids 匹配"。
    """
    wl = session.exec(select(Stock).where(Stock.is_watchlist == True)).all()  # noqa: E712
    if not group_ids:
        return {s.code for s in wl}
    return {s.code for s in wl if any(g in get_group_ids(s) for g in group_ids)}


def add_to_watchlist(session: Session, code: str) -> Stock:
    stock = ensure_stock(session, code)
    stock.is_watchlist = True
    session.add(stock)
    session.commit()
    session.refresh(stock)
    return stock


def remove_from_watchlist(session: Session, code: str) -> None:
    stock = session.get(Stock, code)
    if stock:
        stock.is_watchlist = False
        stock.pinned = False
        session.add(stock)
        session.commit()


def set_pinned(session: Session, code: str, pinned: bool) -> Stock | None:
    stock = session.get(Stock, code)
    if not stock:
        return None
    stock.pinned = pinned
    session.add(stock)
    session.commit()
    session.refresh(stock)
    return stock


def get_group_ids(stock: Stock) -> list[int]:
    if not stock.group_ids:
        # 兼容旧数据：如果有 group_id 但没 group_ids，迁移
        if stock.group_id:
            return [stock.group_id]
        return []
    try:
        ids = json.loads(stock.group_ids)
        return [int(i) for i in ids] if isinstance(ids, list) else []
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def set_group_ids(session: Session, code: str, group_ids: list[int]) -> Stock | None:
    stock = session.get(Stock, code)
    if not stock:
        return None
    stock.group_ids = json.dumps(group_ids) if group_ids else None
    stock.group_id = group_ids[0] if group_ids else None  # 兼容旧字段
    session.add(stock)
    session.commit()
    session.refresh(stock)
    return stock
