"""打分引擎工具函数：线性/三角归一化。"""
from __future__ import annotations


def _norm(x: float | None, lo: float, hi: float) -> float:
    """线性归一化到 [0,1]：x<=lo 得 0，x>=hi 得 1。"""
    if x is None:
        return 0.0
    return min(1.0, max(0.0, (x - lo) / (hi - lo)))


def _tri(x: float | None, lo: float, mid: float, hi: float) -> float:
    """三角归一化：峰值在中点 mid，落在 [lo,hi] 之外为 0（适中最佳）。"""
    if x is None:
        return 0.0
    if x <= lo or x >= hi:
        return 0.0
    if x <= mid:
        return (x - lo) / (mid - lo)
    return (hi - x) / (hi - mid)
