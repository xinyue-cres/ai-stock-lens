"""新浪数据源：兜底用。缺 turnover / amount 自算 / pct_chg 自算。

- 个股日线：ak.stock_zh_a_daily
- 指数日线：ak.stock_zh_index_daily
- 不实现 get_stock_list（走东财）

作为兜底源，不熔断（允许持续调用）。
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from app.datasource.base import Adjust, StockInfo
from app.datasource.base_provider import BaseProvider, Capabilities, sina_symbol

logger = logging.getLogger(__name__)


class SinaProvider(BaseProvider):
    name = "sina"
    capabilities = Capabilities(
        stock_daily=True, index_daily=True, has_turnover=False, stock_list=False,
    )
    # 兜底源不主动熔断；阈值调到极大值即等价于不熔断
    _failure_threshold = 10**9

    def __init__(self) -> None:
        super().__init__()
        import akshare as ak

        self._ak = ak

    def get_stock_list(self) -> list[StockInfo]:
        raise NotImplementedError("SinaProvider 不支持股票列表，走 EastmoneyProvider")

    def get_daily_kline(
        self,
        code: str,
        start: date,
        end: date,
        adjust: Adjust = "qfq",
    ) -> pd.DataFrame:
        symbol = sina_symbol(code)
        raw = self._ak.stock_zh_a_daily(
            symbol=symbol,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust=adjust,
        )
        if raw is None or raw.empty:
            return _empty_kline()

        df = raw.copy()
        df["trade_date"] = pd.to_datetime(df["date"]).dt.date
        df["amount"] = df["close"] * df["volume"]  # 新浪不带 amount，估算
        df["pct_chg"] = df["close"].pct_change().fillna(0) * 100
        df["turnover"] = None  # 新浪不提供换手率
        return df[
            ["trade_date", "open", "high", "low", "close",
             "volume", "amount", "turnover", "pct_chg"]
        ]

    def get_index_daily(self, code: str, start: date, end: date) -> pd.DataFrame:
        df = self._ak.stock_zh_index_daily(symbol=code)
        if df is None or df.empty:
            return _empty_kline()
        df = df.rename(columns={"date": "trade_date"})
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        df = df[(df["trade_date"] >= start) & (df["trade_date"] <= end)]
        if "amount" not in df.columns:
            df["amount"] = df["close"] * df["volume"]
        df["turnover"] = None
        df["pct_chg"] = df["close"].pct_change().fillna(0) * 100
        return df[
            ["trade_date", "open", "high", "low", "close",
             "volume", "amount", "turnover", "pct_chg"]
        ]


def _empty_kline() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["trade_date", "open", "high", "low", "close",
                 "volume", "amount", "turnover", "pct_chg"]
    )
