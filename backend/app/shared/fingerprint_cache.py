"""可复用的进程内指纹缓存：存 (fingerprint, value)，指纹不匹配即视为脏。

适用场景：外部数据（K 线/报告）内容驱动重计算，不想每次手动 invalidate。
fingerprint 由调用方提供（内容 hash 或时间戳等），数据一变指纹就变，自动失效。

实现：粗糙 LRU，超过 capacity 直接清空一半（容量场景个人规模，够用）。
"""
from __future__ import annotations

from typing import Any


class FingerprintedCache:
    """通用 (key -> (fingerprint, value)) 缓存。

    由 analysis_service 的 _ANALYSIS_CACHE 演进而来；适用 K 线指纹 /
    settings 配置 / 高频聚合结果等场景。
    """

    def __init__(self, capacity: int = 200) -> None:
        self._data: dict[str, tuple[str, Any]] = {}
        self._capacity = capacity

    def get(self, key: str, fingerprint: str) -> Any | None:
        """指纹匹配才返回值；指纹变了自动视为脏，返回 None。"""
        hit = self._data.get(key)
        return hit[1] if hit and hit[0] == fingerprint else None

    def set(self, key: str, fingerprint: str, value: Any) -> None:
        """写入。超容量粗糙清一半（非精确 LRU）。"""
        self._data[key] = (fingerprint, value)
        if len(self._data) > self._capacity:
            for k in list(self._data.keys())[: self._capacity // 2]:
                self._data.pop(k, None)

    def invalidate(self, key: str | None = None) -> None:
        """单 key / 全局清空（通常不需要手动调，因为指纹机制本身就自动失效）。"""
        if key is None:
            self._data.clear()
        else:
            self._data.pop(key, None)

    def __contains__(self, key: str) -> bool:
        return key in self._data
