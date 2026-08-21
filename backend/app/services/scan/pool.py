"""扫描候选池构建：按 scope/codes/group_ids 选出要扫的票 + 名称 map。"""
from __future__ import annotations

import logging

from sqlmodel import Session, select

from app.datasource.base_provider import is_fund_code
from app.datasource.router import get_data_router
from app.models.stock import Stock
from app.services.stock_service import watchlist_codes_in_groups

logger = logging.getLogger(__name__)

# ETF/LOF 的缓存门槛：基金历史短、次新多，且 ETF 数据源常晚一天/不足 900 根；
# 放宽到 ≥300 根即可打分（score_stock/_MIN_ROWS=60），避免不足 900 根就走网络拉取→失败→不显示。
_ETF_MIN_BARS = 300


def _min_bars_for(code: str, settings) -> int:
    """打分窗口所需的缓存根数：ETF 放宽（_ETF_MIN_BARS），个股用扫描配置(默认 1000)。"""
    return _ETF_MIN_BARS if is_fund_code(code) else settings.scan_kline_bars


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
