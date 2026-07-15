"""baostock 数据源：作为东财失联时的中间层 fallback。

优点：
- 免费无认证
- 直接返回 turn 字段（换手率 %），无需自算流通股本
- 稳定，接口很少挂
- 支持前复权（adjustflag='2'）/后复权('1')/不复权('3')

缺点：
- 需要 login/logout 全局状态，不能并发
- 只返回日粒度，不支持分钟线
- 昨天的收盘数据要等次日 8:00 后才更新（不适合盘中）
"""
from __future__ import annotations

import logging
import threading
from datetime import date

import pandas as pd

from app.datasource.base import Adjust, StockInfo
from app.datasource.base_provider import BaseProvider, Capabilities

logger = logging.getLogger(__name__)

_bs_lock = threading.Lock()  # baostock 内部用全局状态，不能并发调用


def _bs_symbol(code: str) -> str:
    """将 600519 转成 sh.600519、000001 转成 sz.000001（baostock 要求带前缀）。"""
    if code.startswith(("60", "68", "9")):
        return f"sh.{code}"
    if code.startswith(("00", "30", "20")):
        return f"sz.{code}"
    if code.startswith(("43", "83", "87", "88")):
        return f"bj.{code}"
    return f"sh.{code}"


_ADJUST_FLAG = {"qfq": "2", "hfq": "1", "": "3"}


class BaostockProvider(BaseProvider):
    """baostock 日线 K 线 + 换手率。login/logout 由每次调用负责，避免长连接被服务端断掉。"""

    name = "baostock"
    capabilities = Capabilities(
        stock_daily=True, index_daily=False, has_turnover=True, stock_list=False,
    )

    def __init__(self) -> None:
        super().__init__()
        import baostock as bs

        self._bs = bs

    def get_stock_list(self) -> list[StockInfo]:
        raise NotImplementedError("baostock provider 不用于股票列表，交给 eastmoney")

    def get_daily_kline(
        self,
        code: str,
        start: date,
        end: date,
        adjust: Adjust = "qfq",
    ) -> pd.DataFrame:
        symbol = _bs_symbol(code)
        flag = _ADJUST_FLAG.get(adjust, "2")

        with _bs_lock:
            lg = self._bs.login()
            if lg.error_code != "0":
                logger.warning("baostock login failed: %s", lg.error_msg)
                return self._empty_kline()

            try:
                rs = self._bs.query_history_k_data_plus(
                    symbol,
                    "date,open,high,low,close,volume,amount,turn,pctChg",
                    start_date=start.strftime("%Y-%m-%d"),
                    end_date=end.strftime("%Y-%m-%d"),
                    frequency="d",
                    adjustflag=flag,
                )
                if rs.error_code != "0":
                    logger.warning("baostock query failed %s: %s", symbol, rs.error_msg)
                    return self._empty_kline()

                rows: list[list[str]] = []
                while rs.next():
                    rows.append(rs.get_row_data())
            finally:
                self._bs.logout()

        if not rows:
            return self._empty_kline()

        df = pd.DataFrame(rows, columns=["date", "open", "high", "low", "close",
                                          "volume", "amount", "turn", "pctChg"])
        df["trade_date"] = pd.to_datetime(df["date"]).dt.date
        for col in ["open", "high", "low", "close", "volume", "amount", "turn", "pctChg"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        # baostock 的 volume 是股，amount 是元；口径与东财一致
        return df.rename(columns={"turn": "turnover", "pctChg": "pct_chg"})[
            ["trade_date", "open", "high", "low", "close",
             "volume", "amount", "turnover", "pct_chg"]
        ]

    def get_index_daily(self, code, start, end):  # noqa: D401
        raise NotImplementedError("baostock 不支持指数日线，走 eastmoney/sina")

    def get_capital_flow(self, code: str, start: date, end: date) -> pd.DataFrame | None:
        return None

    def _empty_kline(self) -> pd.DataFrame:
        return pd.DataFrame(
            columns=["trade_date", "open", "high", "low", "close",
                     "volume", "amount", "turnover", "pct_chg"]
        )
