"""DataRouter：按数据种类选 Provider 链，做熔断+fallback 编排。

链定义：
- 个股日线：eastmoney → baostock → sina → tencent
- 指数日线：eastmoney → sina（baostock/tencent 不支持）
- 股票列表：eastmoney（只此一路）
- 权威回填：baostock 直连（不 fallback，专供 backfill 脚本）

调用规则：Provider 抛异常 → record_failure → 下一个；is_healthy=False → 跳过。
全挂返回空 DataFrame，与旧行为一致（不抛给上层）。
"""
from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache

import pandas as pd

from app.datasource.base import Adjust, StockInfo
from app.datasource.base_provider import BaseProvider
from app.datasource.baostock_provider import BaostockProvider
from app.datasource.eastmoney_provider import EastmoneyProvider
from app.datasource.sina_provider import SinaProvider
from app.datasource.tencent_provider import TencentProvider

logger = logging.getLogger(__name__)


class DataRouter:
    """数据源编排器：唯一对外 fetch 入口。"""

    def __init__(
        self,
        eastmoney: EastmoneyProvider,
        baostock: BaostockProvider,
        sina: SinaProvider,
        tencent: TencentProvider,
    ) -> None:
        self._eastmoney = eastmoney
        self._baostock = baostock
        self._sina = sina
        self._tencent = tencent
        self._stock_chain: list[BaseProvider] = [eastmoney, baostock, sina, tencent]
        self._index_chain: list[BaseProvider] = [eastmoney, sina]

    # ---------- 主入口 ----------

    def fetch_stock_daily(
        self,
        code: str,
        start: date,
        end: date,
        adjust: Adjust = "qfq",
    ) -> pd.DataFrame:
        return self._try_chain(
            self._stock_chain,
            lambda p: p.get_daily_kline(code, start, end, adjust),
            context=f"stock_daily {code}",
        )

    def fetch_index_daily(self, code: str, start: date, end: date) -> pd.DataFrame:
        return self._try_chain(
            self._index_chain,
            lambda p: p.get_index_daily(code, start, end),
            context=f"index_daily {code}",
        )

    def fetch_stock_daily_authoritative(
        self,
        code: str,
        start: date,
        end: date,
        adjust: Adjust = "qfq",
    ) -> pd.DataFrame:
        """回填/校准专用：直连 baostock 拿权威数据，不 fallback。"""
        return self._baostock.get_daily_kline(code, start, end, adjust)

    def get_stock_list(self) -> list[StockInfo]:
        """全 A 股列表：只走东财。"""
        return self._eastmoney.get_stock_list()

    def get_health(self) -> list[dict]:
        """各 provider 当前健康状态。"""
        import time
        now = time.time()
        result = []
        for p in self._stock_chain:
            cooldown = p._cooldown_until
            result.append({
                "name": p.name,
                "healthy": p.is_healthy(),
                "failures": p._failures,
                "cooldown_remaining": max(0, int(cooldown - now)) if cooldown > 0 else 0,
            })
        return result

    # ---------- 内部 ----------

    def _try_chain(self, chain: list[BaseProvider], call, context: str) -> pd.DataFrame:
        last_error: Exception | None = None
        for provider in chain:
            if not provider.is_healthy():
                logger.debug("[%s] skip %s (cooling down)", context, provider.name)
                continue
            try:
                df = call(provider)
                if df is not None and not df.empty:
                    provider.record_success()
                    logger.info("[%s] %s OK · %d rows", context, provider.name, len(df))
                    return df
                logger.info("[%s] %s returned empty, trying next", context, provider.name)
            except NotImplementedError:
                # 明确不支持不算失败，直接跳
                continue
            except Exception as e:  # noqa: BLE001
                logger.warning("[%s] %s failed (%s): %s",
                               context, provider.name, type(e).__name__, e)
                provider.record_failure()
                last_error = e

        # 全链条走完仍无数据：返回空 DataFrame（与旧 provider 行为一致）
        if last_error is not None:
            logger.warning("[%s] 所有源均失败，最后错误：%s", context, last_error)
        return _empty_kline()


def _empty_kline() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["trade_date", "open", "high", "low", "close",
                 "volume", "amount", "turnover", "pct_chg"]
    )


@lru_cache(maxsize=1)
def get_data_router() -> DataRouter:
    """模块级单例。首次调用时懒加载四个 Provider。"""
    return DataRouter(
        eastmoney=EastmoneyProvider(),
        baostock=BaostockProvider(),
        sina=SinaProvider(),
        tencent=TencentProvider(),
    )
