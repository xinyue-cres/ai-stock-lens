"""选股扫描"K 线最新性"单元测试：缓存最新性判定。

覆盖纯逻辑部分：
- _is_stale：缓存最后根是否落后到今天（跳周末，不算节假日）
- _cache_needs_pull：判定该缓存窗口是否需要补拉（无数据/落后 → True）
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from app.services.scoring_service import _cache_needs_pull, _is_stale


def _mk_df(last_date: date) -> pd.DataFrame:
    return pd.DataFrame([
        {
            "trade_date": last_date, "open": 1.0, "high": 1.01, "low": 0.99,
            "close": 1.0, "volume": 1_000_000, "amount": 1_000_000,
            "turnover": 1.5, "pct_chg": 0.0,
        }
    ])


class TestIsStale:
    def test_none_is_stale(self):
        assert _is_stale(None, date(2026, 8, 17)) is True

    def test_same_day_fresh(self):
        d = date(2026, 8, 17)  # 周一
        assert _is_stale(d, d) is False

    def test_previous_trading_day_fresh_on_weekend(self):
        # 周五收盘数据在周六/周日不算落后
        friday = date(2026, 8, 14)
        assert _is_stale(friday, date(2026, 8, 15)) is False  # 周六
        assert _is_stale(friday, date(2026, 8, 16)) is False  # 周日

    def test_monday_behind_full_weekend_is_stale(self):
        # 周一开盘后再扫描：库里只有上周四 → 落后（周一、… 与今天差）≥1 交易日
        thursday = date(2026, 8, 13)
        assert _is_stale(thursday, date(2026, 8, 17)) is True

    def test_friday_behind_next_monday_is_stale(self):
        friday = date(2026, 8, 14)
        assert _is_stale(friday, date(2026, 8, 17)) is True


class TestIsStaleGrace:
    """ETF 档位（grace=1）：允许 K 线滞后 1 个交易日仍算最新（数据源天然晚一天）。"""

    def test_one_day_behind_not_stale_with_grace(self):
        # 个股(grace=0)判定为旧；ETF(grace=1)允许滞后 1 交易日 → 昨日数据仍最新
        friday = date(2026, 8, 14)
        monday = date(2026, 8, 17)
        assert _is_stale(friday, monday, grace=0) is True
        assert _is_stale(friday, monday, grace=1) is False

    def test_two_days_behind_stale_even_with_grace(self):
        # 滞后 2 个交易日后，即便 ETF 也判为旧
        thursday = date(2026, 8, 13)
        monday = date(2026, 8, 17)
        assert _is_stale(thursday, monday, grace=1) is True

    def test_none_always_stale(self):
        assert _is_stale(None, date(2026, 8, 17), grace=1) is True


class TestCacheNeedsPull:
    """判定缓存是否需补拉（无数据/落后 → True；已最新 → False，纯判定不触发 IO）。"""

    def test_none_df_needs_pull(self):
        assert _cache_needs_pull(None, date(2026, 8, 17)) is True

    def test_empty_df_needs_pull(self):
        assert _cache_needs_pull(pd.DataFrame(), date(2026, 8, 17)) is True

    def test_fresh_no_pull(self):
        today = date(2026, 8, 17)
        assert _cache_needs_pull(_mk_df(today), today) is False

    def test_stale_needs_pull(self):
        assert _cache_needs_pull(_mk_df(date(2026, 8, 14)), date(2026, 8, 17)) is True

    def test_etf_yesterday_no_pull_with_grace(self):
        # 个股(grace=0)需要补拉；ETF(grace=1)昨日数据不补拉
        today = date(2026, 8, 17)
        assert _cache_needs_pull(_mk_df(date(2026, 8, 14)), today, grace=0) is True
        assert _cache_needs_pull(_mk_df(date(2026, 8, 14)), today, grace=1) is False
