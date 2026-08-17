"""选股扫描"K 线最新性"单元测试：缓存最新性判定与增量补拉快路径。

覆盖纯逻辑部分：
- _is_stale：缓存最后根是否落后到今天（跳周末，不算节假日）
- _ensure_fresh_cache 的 already_fresh 快路径（缓存已最新时不触发同步/DB 访问）
"""
from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.services.scoring_service import _ensure_fresh_cache, _is_stale


def _noop_session(*_a, **_k):
    raise AssertionError("已最新时不应当访问 DB / 触发同步")


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


class TestEnsureFreshCacheAlreadyFresh:
    """缓存已最新 → 快路径：直接返回原 df，不触碰 DB/不触发同步。"""

    def test_fresh_returns_df(self):
        today = date(2026, 8, 17)
        df = _mk_df(today)  # 最后根就是今天 → 非 stale
        out, diag = _ensure_fresh_cache(_noop_session, "000001", df, None, today)
        assert out is df
        assert diag["pulled"] is False
        assert diag["reason"] == "already_fresh"
