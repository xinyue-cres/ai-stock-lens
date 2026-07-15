"""数据源统一契约：Provider 都返回同样列名的 DataFrame。

编排（多源 fallback / 熔断）不在这里，看 `router.DataRouter`。
Provider 基类和熔断实现在 `base_provider.py`。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal, Protocol

import pandas as pd


@dataclass
class StockInfo:
    code: str
    name: str
    market: str


Adjust = Literal["", "qfq", "hfq"]


class DataSource(Protocol):
    """Provider 需要实现的接口。

    日线 columns: [trade_date, open, high, low, close, volume, amount, turnover, pct_chg]
    资金流 columns: [trade_date, main_net, super_large, large, medium, small]

    个别 Provider 可能只支持部分能力（比如 baostock 不支持指数日线），能力声明在
    Provider.capabilities 上；调用方应通过 DataRouter 而不是直接调 Provider。
    """

    name: str

    def get_stock_list(self) -> list[StockInfo]:
        ...

    def get_daily_kline(
        self, code: str, start: date, end: date, adjust: Adjust = "qfq",
    ) -> pd.DataFrame:
        ...

    def get_index_daily(self, code: str, start: date, end: date) -> pd.DataFrame:
        ...
