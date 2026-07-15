"""analysis_service 缓存单元测试：验证内容 hash 指纹自动感知 K 线变化。"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from app.services.analysis_service import _fingerprint, _ANALYSIS_CACHE, invalidate_analysis_cache


def _mk_df(n=10, mutate: dict | None = None):
    """构造 n 行合法 K 线；mutate={"turnover": 5.0} 修改最后一行某字段。"""
    base_date = date(2026, 1, 1)
    rows = []
    for i in range(n):
        rows.append({
            "trade_date": base_date + timedelta(days=i),
            "open": 10.0 + i * 0.1,
            "high": 11.0 + i * 0.1,
            "low": 9.0 + i * 0.1,
            "close": 10.5 + i * 0.1,
            "volume": 1000 * (i + 1),
            "amount": 10500.0 * (i + 1),
            "turnover": 1.0 + i * 0.05,
            "pct_chg": 0.5,
        })
    df = pd.DataFrame(rows)
    if mutate:
        for k, v in mutate.items():
            df.loc[df.index[-1], k] = v
    return df


def test_fingerprint_stable_for_same_data():
    df1 = _mk_df(20)
    df2 = _mk_df(20)
    assert _fingerprint(df1) == _fingerprint(df2)


def test_fingerprint_changes_on_turnover_modification():
    """回填修改 turnover 字段 → 指纹变化 → 缓存自动失效"""
    df1 = _mk_df(20)
    df2 = _mk_df(20, mutate={"turnover": 999.0})
    assert _fingerprint(df1) != _fingerprint(df2)


def test_fingerprint_changes_on_volume_correction():
    """回填修正 volume（603733 那种 100 倍量级错误）→ 指纹变化"""
    df1 = _mk_df(20)
    df2 = _mk_df(20, mutate={"volume": 999999})
    assert _fingerprint(df1) != _fingerprint(df2)


def test_fingerprint_changes_on_new_row():
    """增量同步新增一行 → 指纹变化"""
    df1 = _mk_df(20)
    df2 = _mk_df(21)
    assert _fingerprint(df1) != _fingerprint(df2)


def test_fingerprint_changes_on_pct_chg_backfill():
    """pct_chg 从 0 修复为 9.99 → 指纹变化"""
    df1 = _mk_df(20, mutate={"pct_chg": 0.0})
    df2 = _mk_df(20, mutate={"pct_chg": 9.99})
    assert _fingerprint(df1) != _fingerprint(df2)


def test_invalidate_still_works():
    """保留的 invalidate_analysis_cache 接口仍生效（调试用）"""
    _ANALYSIS_CACHE.clear()
    _ANALYSIS_CACHE["600519"] = ("fake_fingerprint", {"cached": True})
    invalidate_analysis_cache("600519")
    assert "600519" not in _ANALYSIS_CACHE
