"""选股扫描包：按职责拆为 state / pool / kline_cache / writer / runner 五个模块。

对外公开接口与原 services/scoring_service.py 完全一致：
- scan_market / get_scan_status / cancel_scan   扫描控制
- _load_cached_kline / _parse_as_of              K 线缓存读取（scripts / migrate 用）
- _cache_needs_pull / _is_stale                  新鲜度判定（tests 用）
"""
from .kline_cache import (  # noqa: F401
    _cache_needs_pull,
    _is_intraday_now,
    _is_stale,
    _latest_db_dates,
    _load_cached_kline,
    _parse_as_of,
)
from .runner import _build_plan, _run_scan, scan_market  # noqa: F401
from .state import cancel_scan, get_scan_status  # noqa: F401
from .writer import _combined_upsert, _upsert  # noqa: F401
