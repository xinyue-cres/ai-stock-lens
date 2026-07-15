"""腾讯行情快照数据源：最低优先级兜底。

用 ak.stock_zh_a_spot()（腾讯接口）拿全市场实时/收盘快照，从中提取
单只股票当天的 OHLCV 构造日 K 线行。

特点：
- 收盘后立即可用（~15:01），不像 baostock/新浪要等 17:00+
- 只能拿"今天"一行数据，不能拿历史
- 没有前复权（但只差一天不影响）
- 换手率字段有时为 0（看腾讯返回质量）

作为最低优先级兜底，只在东财+baostock+新浪全部返回空时才会被调用。
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from app.datasource.base import Adjust, StockInfo
from app.datasource.base_provider import BaseProvider, Capabilities, infer_market

logger = logging.getLogger(__name__)


class TencentProvider(BaseProvider):
    name = "tencent"
    capabilities = Capabilities(
        stock_daily=True, index_daily=False, has_turnover=True, stock_list=False,
    )
    _failure_threshold = 10**9

    def __init__(self) -> None:
        super().__init__()
        import akshare as ak
        self._ak = ak
        self._spot_cache: pd.DataFrame | None = None
        self._spot_cache_ts: float = 0

    def _get_spot(self) -> pd.DataFrame:
        """全市场快照，60 秒内复用缓存。"""
        import time
        now = time.time()
        if self._spot_cache is not None and (now - self._spot_cache_ts) < 60:
            return self._spot_cache
        df = self._ak.stock_zh_a_spot()
        if df is not None and not df.empty:
            self._spot_cache = df
            self._spot_cache_ts = now
            return df
        return pd.DataFrame()

    def get_stock_list(self) -> list[StockInfo]:
        raise NotImplementedError("TencentProvider 不支持股票列表")

    def get_daily_kline(
        self,
        code: str,
        start: date,
        end: date,
        adjust: Adjust = "qfq",
    ) -> pd.DataFrame:
        today = date.today()
        if today < start or today > end:
            return _empty_kline()

        df = self._get_spot()
        if df.empty:
            return _empty_kline()

        # 腾讯接口代码格式为 sz002379 / sh600519 / bj430047
        tencent_code = f"{infer_market(code).lower()}{code}"
        row = df[df["代码"] == tencent_code]
        if row.empty:
            return _empty_kline()

        r = row.iloc[0]
        close = _float(r.get("最新价"))
        if close is None or close <= 0:
            return _empty_kline()

        open_ = _float(r.get("今开"))
        high = _float(r.get("最高"))
        low = _float(r.get("最低"))
        volume = _float(r.get("成交量"))
        amount = _float(r.get("成交额"))
        turnover = _float(r.get("换手率"))
        pct_chg = _float(r.get("涨跌幅"))

        return pd.DataFrame([{
            "trade_date": today,
            "open": open_ or close,
            "high": high or close,
            "low": low or close,
            "close": close,
            "volume": volume or 0,
            "amount": amount or 0,
            "turnover": turnover if turnover and turnover > 0 else None,
            "pct_chg": pct_chg or 0,
        }])

    def get_index_daily(self, code: str, start: date, end: date) -> pd.DataFrame:
        raise NotImplementedError("TencentProvider 不支持指数日线")


def _float(v) -> float | None:
    try:
        f = float(v)
        return f if f == f else None  # NaN check
    except (TypeError, ValueError):
        return None


def _empty_kline() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["trade_date", "open", "high", "low", "close",
                 "volume", "amount", "turnover", "pct_chg"]
    )
