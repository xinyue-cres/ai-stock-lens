"""多股对比服务。"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from sqlmodel import Session, select

from app.models.stock import Stock
from app.services.analysis_service import load_kline_df
from app.services.compare_math import normalize, pct_change


def compare_stocks(session: Session, codes: list[str], days: int = 120) -> dict:
    """多股对比，返回归一化走势 + 阶段涨幅 + 最新价。

    - 归一化以 codes 交集的最早共同日期为基准（避免上市时间不齐拉扯）
    """
    if not codes:
        return {"items": [], "dates": []}

    per_stock: list[dict] = []
    dfs: list[pd.DataFrame] = []

    for code in codes:
        stock = session.get(Stock, code)
        df = load_kline_df(session, code, days=days)
        if df.empty:
            per_stock.append({"code": code, "name": stock.name if stock else None, "empty": True})
            dfs.append(pd.DataFrame())
            continue

        df = df.sort_values("trade_date").reset_index(drop=True)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df.set_index("trade_date")
        dfs.append(df)

        close = df["close"]
        per_stock.append(
            {
                "code": code,
                "name": stock.name if stock else None,
                "market": stock.market if stock else None,
                "latest_close": float(close.iloc[-1]),
                "pct_5d": pct_change(close, 5),
                "pct_20d": pct_change(close, 20),
                "pct_60d": pct_change(close, 60) if len(close) >= 61 else None,
            }
        )

    # 归一化：取所有非空 df 的共同日期
    non_empty = [df for df in dfs if not df.empty]
    if not non_empty:
        return {"items": per_stock, "dates": []}

    tail = date.today() - timedelta(days=days)
    common_index = None
    for df in non_empty:
        idx = df.index[df.index >= pd.Timestamp(tail)]
        common_index = idx if common_index is None else common_index.intersection(idx)

    if common_index is None or len(common_index) == 0:
        # 退化：各自独立归一化
        for i, df in enumerate(dfs):
            if not df.empty:
                per_stock[i]["norm"] = list(zip(
                    [d.strftime("%Y-%m-%d") for d in df.index],
                    normalize(df["close"]),
                ))
        return {"items": per_stock, "dates": []}

    common_index = common_index.sort_values()
    for i, df in enumerate(dfs):
        if df.empty:
            continue
        series = df.loc[common_index, "close"]
        per_stock[i]["norm"] = list(zip(
            [d.strftime("%Y-%m-%d") for d in common_index],
            normalize(series),
        ))

    return {
        "items": per_stock,
        "dates": [d.strftime("%Y-%m-%d") for d in common_index],
    }


def list_watchlist_codes(session: Session) -> list[str]:
    stmt = select(Stock.code).where(Stock.is_watchlist == True)  # noqa: E712
    return list(session.exec(stmt))
