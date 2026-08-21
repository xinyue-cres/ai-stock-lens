"""扫描全局状态：单实例进度追踪 + 线程安全读写。

_scan_state 由 runner 线程写、API/UI 层读；所有读写必须过 _scan_lock。
无外部业务依赖——纯粹的状态机。
"""
from __future__ import annotations

import threading

_scan_lock = threading.Lock()
_scan_state: dict = {
    "running": False,
    "scope": None,
    "total": 0,
    "done": 0,
    "failed": 0,
    "current": None,
    "started_at": None,
    "finished_at": None,
    "cancel_requested": False,
}


def _state(mutate: bool = False) -> dict:
    if mutate:
        return _scan_state
    with _scan_lock:
        return dict(_scan_state)


def get_scan_status() -> dict:
    """当前扫描进度（前端轮询用）。"""
    with _scan_lock:
        return dict(_scan_state)


def cancel_scan() -> dict:
    """请求取消进行中的扫描。"""
    with _scan_lock:
        _scan_state["cancel_requested"] = True
        running = _scan_state["running"]
    return {"ok": True, "running": running}
