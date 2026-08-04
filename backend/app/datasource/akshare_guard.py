"""akshare 调用锁代理（按方法区分）。

akshare 的新浪系接口（stock_zh_a_daily / stock_zh_index_daily / fund_etf_hist_sina /
fund_etf_category_sina / stock_zh_a_spot 等）依赖 py_mini_racer(V8)，V8 非线程安全——
多线程并发初始化/使用会触发 FATAL（address_pool_manager Check failed）导致进程崩溃，
实测在扫描高并发降级到新浪源时触发。因此**只有这些接口**必须串行化。

东财系接口（stock_zh_a_hist / stock_zh_index_daily_em / stock_info_a_code_name 及
分红表 stock_fhps_em 等）是纯 requests，不用 V8，可多线程并发——不加锁，让同步
并发化真正提速。

用法：provider 里用 `self._ak = get_ak()` 替代 `import akshare as ak; self._ak = ak`。
"""
from __future__ import annotations

import threading

AK_LOCK = threading.Lock()

# 依赖 V8（py_mini_racer）必须串行的 akshare 方法：新浪系历史数据有 JS 加密。
# 不在白名单的接口（东财纯 requests）直接返回原始函数，可并发。
_V8_METHODS = {
    "stock_zh_a_daily",
    "stock_zh_index_daily",
    "fund_etf_hist_sina",
    "fund_etf_category_sina",
    "stock_zh_a_spot",
}

_ak_cache: dict[str, object] = {}


class _LockedAk:
    """akshare 模块代理：仅 V8 相关方法加全局锁，其余方法直接透传可并发。"""

    def __init__(self, module: object) -> None:
        self._module = module

    def __getattr__(self, name: str):
        attr = getattr(self._module, name)
        if callable(attr):
            if name in _V8_METHODS:
                def locked(*args, **kwargs):
                    with AK_LOCK:
                        return attr(*args, **kwargs)

                return locked
            return attr
        return attr


def get_ak() -> _LockedAk:
    """返回锁代理 akshare（真实模块只 import 一次）。"""
    if "ak" not in _ak_cache:
        import akshare as ak

        _ak_cache["ak"] = _LockedAk(ak)
    return _ak_cache["ak"]  # type: ignore[return-value]
