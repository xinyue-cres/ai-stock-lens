"""DataRouter 单元测试：验证 fallback/熔断/权威回填的编排逻辑。

不引入真实数据源；用 Mock Provider 注入 Router。
"""
from __future__ import annotations

import time
from datetime import date

import pandas as pd
import pytest

from app.datasource.base_provider import BaseProvider, Capabilities
from app.datasource.router import DataRouter


def _df(n_rows: int = 3) -> pd.DataFrame:
    """构造一个 n 行的合法 K 线 DataFrame。"""
    return pd.DataFrame({
        "trade_date": [date(2026, 1, i + 1) for i in range(n_rows)],
        "open": [10.0] * n_rows, "high": [11.0] * n_rows,
        "low": [9.0] * n_rows,  "close": [10.5] * n_rows,
        "volume": [1000] * n_rows, "amount": [10500.0] * n_rows,
        "turnover": [1.5] * n_rows, "pct_chg": [0.5] * n_rows,
    })


class MockProvider(BaseProvider):
    """可编程行为的 Provider：由 behavior 决定 get_daily_kline 结果。"""

    def __init__(self, name: str, behavior: str = "success") -> None:
        super().__init__()
        self.name = name
        self.capabilities = Capabilities(stock_daily=True, index_daily=True)
        self.behavior = behavior  # "success" / "raise" / "empty"
        self.calls: int = 0

    def get_daily_kline(self, code, start, end, adjust="qfq"):
        self.calls += 1
        if self.behavior == "raise":
            raise RuntimeError(f"{self.name} explode")
        if self.behavior == "empty":
            return pd.DataFrame()
        return _df()

    def get_index_daily(self, code, start, end):
        return self.get_daily_kline(code, start, end)


@pytest.fixture
def mk_router():
    """构造带 mock 三源的 Router 的工厂。"""
    def _make(em="success", bs="success", sn="success"):
        em_p = MockProvider("eastmoney", em)
        bs_p = MockProvider("baostock", bs)
        sn_p = MockProvider("sina", sn)
        r = DataRouter(eastmoney=em_p, baostock=bs_p, sina=sn_p)  # type: ignore[arg-type]
        return r, em_p, bs_p, sn_p
    return _make


def test_primary_success_stops_at_first(mk_router):
    """主源成功，链路不再往下调。"""
    r, em, bs, sn = mk_router(em="success")
    df = r.fetch_stock_daily("600519", date(2026, 1, 1), date(2026, 1, 3))
    assert not df.empty
    assert em.calls == 1
    assert bs.calls == 0
    assert sn.calls == 0


def test_primary_raise_falls_through_and_records(mk_router):
    """主源抛异常 → 走下一个 + record_failure。"""
    r, em, bs, sn = mk_router(em="raise", bs="success")
    df = r.fetch_stock_daily("600519", date(2026, 1, 1), date(2026, 1, 3))
    assert not df.empty
    assert em.calls == 1
    assert bs.calls == 1
    assert em._failures == 1
    assert bs._failures == 0


def test_primary_cooling_down_is_skipped(mk_router):
    """主源冷却期内直接跳过，不发起调用。"""
    r, em, bs, sn = mk_router(em="raise", bs="success")
    # 手动让主源进入冷却
    em._cooldown_until = time.time() + 60
    df = r.fetch_stock_daily("600519", date(2026, 1, 1), date(2026, 1, 3))
    assert not df.empty
    assert em.calls == 0  # 不再调用
    assert bs.calls == 1


def test_all_fail_returns_empty(mk_router):
    """全链失败：返回空 DataFrame，不抛异常。"""
    r, em, bs, sn = mk_router(em="raise", bs="raise", sn="raise")
    df = r.fetch_stock_daily("600519", date(2026, 1, 1), date(2026, 1, 3))
    assert df.empty
    assert em.calls == 1
    assert bs.calls == 1
    assert sn.calls == 1


def test_authoritative_bypasses_chain(mk_router):
    """权威回填直连 baostock，主源挂了它也不受影响。"""
    r, em, bs, sn = mk_router(em="raise", bs="success", sn="raise")
    df = r.fetch_stock_daily_authoritative("600519", date(2026, 1, 1), date(2026, 1, 3))
    assert not df.empty
    assert em.calls == 0
    assert bs.calls == 1
    assert sn.calls == 0


def test_empty_result_falls_through(mk_router):
    """主源返回空 DataFrame 不算失败，但仍尝试下一个。"""
    r, em, bs, sn = mk_router(em="empty", bs="success")
    df = r.fetch_stock_daily("600519", date(2026, 1, 1), date(2026, 1, 3))
    assert not df.empty
    assert em.calls == 1
    assert bs.calls == 1
    assert em._failures == 0  # 空结果不记失败
