"""多股对比服务的最小烟雾测试（不依赖 DB，直接测归一化函数）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.compare_math import normalize, pct_change


def test_normalize_basic():
    s = pd.Series([10.0, 11.0, 12.5, 9.0])
    out = normalize(s)
    assert out[0] == 100.0
    assert out[1] == 110.0
    assert out[2] == 125.0
    assert out[3] == 90.0
    print("✓ normalize 基本用例通过")


def test_normalize_zero_base():
    s = pd.Series([0.0, 1.0, 2.0])
    out = normalize(s)
    assert all(v == 100.0 for v in out), "0 基准应全部返回 100 兜底"
    print("✓ normalize 零基准兜底通过")


def test_normalize_empty():
    assert normalize(pd.Series(dtype=float)) == []
    print("✓ normalize 空序列通过")


def test_pct_change():
    s = pd.Series([10.0] * 30 + [12.0])  # 31 个点，20 日前是 10.0，最新 12.0
    assert pct_change(s, 20) == 20.0
    assert pct_change(s, 100) is None  # 长度不够
    print("✓ pct_change 通过")


if __name__ == "__main__":
    test_normalize_basic()
    test_normalize_zero_base()
    test_normalize_empty()
    test_pct_change()
