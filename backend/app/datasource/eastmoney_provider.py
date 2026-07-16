"""东财数据源：字段最全（含 turnover、pct_chg），但连接不稳。

- 个股日线：ak.stock_zh_a_hist
- 指数日线：ak.stock_zh_index_daily_em
- 股票列表：ak.stock_info_a_code_name

熔断由 BaseProvider 提供；本类不做 fallback。
"""
from __future__ import annotations

import logging
from datetime import date
from functools import lru_cache
from typing import Literal

import pandas as pd

from app.datasource.base import Adjust, StockInfo
from app.datasource.base_provider import BaseProvider, Capabilities, infer_market, is_fund_code

logger = logging.getLogger(__name__)


class EastmoneyProvider(BaseProvider):
    name = "eastmoney"
    capabilities = Capabilities(
        stock_daily=True, index_daily=True, has_turnover=True, stock_list=True,
    )

    def __init__(self) -> None:
        super().__init__()
        import akshare as ak

        self._ak = ak

    @lru_cache(maxsize=1)
    def get_stock_list(self) -> list[StockInfo]:
        results: list[StockInfo] = []

        # A 股股票
        df = self._ak.stock_info_a_code_name()
        for _, row in df.iterrows():
            results.append(StockInfo(code=row["code"], name=row["name"], market=infer_market(row["code"])))

        # 场内基金（ETF + LOF）
        for category in ("ETF基金", "LOF基金"):
            try:
                fdf = self._ak.fund_etf_category_sina(symbol=category)
                for _, row in fdf.iterrows():
                    raw_code = str(row["代码"])
                    code = raw_code[-6:]  # "sz159998" -> "159998"
                    results.append(StockInfo(code=code, name=row["名称"], market=infer_market(code)))
            except Exception:
                logger.warning("拉取 %s 列表失败，跳过", category)

        return results

    def get_daily_kline(
        self,
        code: str,
        start: date,
        end: date,
        adjust: Adjust = "qfq",
    ) -> pd.DataFrame:
        if is_fund_code(code):
            return self._get_fund_kline(code, start, end)

        raw = self._ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
            adjust=adjust,
        )
        if raw is None or raw.empty:
            return _empty_kline()
        return raw.rename(
            columns={
                "日期": "trade_date",
                "开盘": "open",
                "最高": "high",
                "最低": "low",
                "收盘": "close",
                "成交量": "volume",
                "成交额": "amount",
                "换手率": "turnover",
                "涨跌幅": "pct_chg",
            }
        )[["trade_date", "open", "high", "low", "close", "volume", "amount", "turnover", "pct_chg"]]

    def _get_fund_kline(self, code: str, start: date, end: date) -> pd.DataFrame:
        """场内基金日线：使用 fund_etf_hist_sina 接口。"""
        symbol = f"{infer_market(code).lower()}{code}"
        raw = self._ak.fund_etf_hist_sina(symbol=symbol)
        if raw is None or raw.empty:
            return _empty_kline()
        df = raw.copy()
        df["trade_date"] = pd.to_datetime(df["date"]).dt.date
        df = df[(df["trade_date"] >= start) & (df["trade_date"] <= end)]
        if df.empty:
            return _empty_kline()
        for col in ["open", "high", "low", "close", "volume", "amount"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        df["pct_chg"] = df["close"].pct_change().fillna(0) * 100
        df["turnover"] = None
        return df[["trade_date", "open", "high", "low", "close", "volume", "amount", "turnover", "pct_chg"]]

    def get_index_daily(self, code: str, start: date, end: date) -> pd.DataFrame:
        """指数日线。code 格式 sh000001 / sz399001。"""
        df = self._ak.stock_zh_index_daily_em(symbol=code)
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
            ["trade_date", "open", "high", "low", "close", "volume", "amount", "turnover", "pct_chg"]
        ]


def _empty_kline() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["trade_date", "open", "high", "low", "close",
                 "volume", "amount", "turnover", "pct_chg"]
    )
