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

_patcher_installed = False


def install_tls_patch() -> None:
    """让 akshare（requests）忽略 HTTPS 证书校验。

    背景：本机系统代理（Whistle）对部分数据源域名做 SSL 拦截/转发，且 Python 默认
    证书链在该环境下对这些 https 源验证失败（CERTIFICATE_VERIFY_FAILED），导致数据源
    拉取 K 线/列表失败。经实测：requests 设置 verify=False 后各数据源可连通（新浪/深交所
    直连 200，eastmoney 由 provider 链 fallback 到可用源）。这里对 requests.Session.request
    打一次性补丁，强制 verify=False。只影响 requests（数据源/akshare），AI 走 openai(httpx) 不受影响。

    幂等：重复调用只装一次。
    """
    global _patcher_installed
    if _patcher_installed:
        return
    import requests  # noqa: PLC0415
    import urllib3  # noqa: PLC0415
    from urllib3.exceptions import InsecureRequestWarning

    urllib3.disable_warnings(InsecureRequestWarning)
    _orig = requests.sessions.Session.request

    def _request_ignore_verify(self, method: str, url: str, **kwargs):
        kwargs["verify"] = False
        return _orig(self, method, url, **kwargs)

    requests.sessions.Session.request = _request_ignore_verify
    _patcher_installed = True


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
    """返回锁代理 akshare（真实模块只 import 一次）。

    首次使用时同时确保 TLS 忽略校验补丁已装（幂等），覆盖非 FastAPI 路径（scheduler/run.py/测试）。
    """
    install_tls_patch()
    if "ak" not in _ak_cache:
        import akshare as ak

        _ak_cache["ak"] = _LockedAk(ak)
    return _ak_cache["ak"]  # type: ignore[return-value]
