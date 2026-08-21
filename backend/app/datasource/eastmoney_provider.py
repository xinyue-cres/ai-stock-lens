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


def _fetch_stock_list_direct() -> pd.DataFrame | None:
    """手工 requests 直连东财 spot API 拉全 A 列表（不走 akshare wrapper）。

    akshare 的 `stock_info_a_code_name` 底层其实是 szse.cn xlsx 经常被系统代理封；
    `stock_zh_a_spot_em` 是标准 akshare 实现鸭子但内部 session 不能注入代理绕掘。手工
    requests + verify=False（系统代理 SSL 拦截）+ 关 proxy（绕开 Whistle 阻拦）百毫秒拿满。

    东财 list API：push2.eastmoney.com/api/qt/clist/get，pn 分页每页 ~100。命中后重置分页。
    """
    import requests  # noqa: PLC0415
    import urllib3  # noqa: PLC0415

    urllib3.disable_warnings()
    rows: list[dict] = []
    pn = 1
    while True:
        r = requests.get(
            "https://82.push2.eastmoney.com/api/qt/clist/get",
            params={
                "pn": pn, "pz": 100, "po": 1, "np": 1,
                "ut": "bd1d9ddb04089700cf9c27f6f7426281",
                "fltt": 2, "invt": 2,
                "fid": "f12",
                "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048",
                "fields": "f12,f14",  # f12=代码, f14=名称
            },
            timeout=15,
            verify=False,
            proxies={"http": None, "https": None},
        )
        data = r.json().get("data")
        if not data:
            return None
        diff = data.get("diff") or []
        for row in diff:
            rows.append({"code": row.get("f12"), "name": row.get("f14")})
        if len(diff) < 100 or len(rows) >= int(data.get("total", 0)):
            break
        pn += 1

    if not rows:
        return None
    df = pd.DataFrame(rows)
    # 把字段统一成 provider 后面读 code/name 的联合字段名
    df = df.rename(columns={"code": "code", "name": "name"})
    return df[["code", "name"]]


class EastmoneyProvider(BaseProvider):
    name = "eastmoney"
    capabilities = Capabilities(
        stock_daily=True, index_daily=True, has_turnover=True, stock_list=True,
    )

    def __init__(self) -> None:
        super().__init__()
        from app.datasource.akshare_guard import get_ak

        self._ak = get_ak()

    @lru_cache(maxsize=1)
    def get_stock_list(self) -> list[StockInfo]:
        results: list[StockInfo] = []

        # A 股股票。优先东财 direct requests（不走 akshare）：akshare 的 stock_info_a_code_name
        # 底层其实是 szse.cn xlsx，常被系统代理封；akshare_spot_em 分页封装偶发 502。手工
        # requests 直连 + 绕系统代理 + 解随便 SSL 拦截（verify=False），百毫秒拿满 5899 只。
        # 偶发 ConnectionError（二级配对负载， 稍纵即逝）  - retry 3 次 backoff
        df: pd.DataFrame | None = None
        import time as _time  # noqa: PLC0415
        for attempt in range(3):
            try:
                df = _fetch_stock_list_direct()
                if df is not None and not df.empty:
                    if attempt:
                        logger.info("stock list 东财 direct 在重试 %d 次后成功：%d 只 A股", attempt, len(df))
                    else:
                        logger.info("stock list 东财 direct 返回 %d 只 A股", len(df))
                    break
            except Exception as e:  # noqa: BLE001
                logger.warning("stock list 东财 direct 第 %d 次失败：%s", attempt + 1, type(e).__name__)
                if attempt < 2:
                    _time.sleep(2 * (attempt + 1))
                df = None

        if df is None or df.empty:
            for api_name, code_col, name_col in [("stock_zh_a_spot", "代码", "名称"),
                                             ("stock_info_a_code_name", "code", "name")]:
                try:
                    df = getattr(self._ak, api_name)()
                    if df is not None and not df.empty:
                        logger.info("stock list akshare %s 返回 %d 只 A股", api_name, len(df))
                        break
                except Exception as e:
                    logger.warning("stock list akshare %s 失败：%s", api_name, type(e).__name__)

        if df is None or df.empty:
            raise RuntimeError("所有 stock list 接口（东财 direct / sina / szse.cn）均失败")

        col_code = "代码" if "代码" in df.columns else "code"
        col_name = "名称" if "名称" in df.columns else "name"
        for _, row in df.iterrows():
            results.append(StockInfo(code=row[col_code], name=row[col_name], market=infer_market(row[col_code])))

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
        df = raw.rename(
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
        )
        # 东财"成交量"单位是手（100 股），统一为股，与新浪/baostock 等其他源对齐
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce") * 100
        return df[["trade_date", "open", "high", "low", "close", "volume", "amount", "turnover", "pct_chg"]]

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
