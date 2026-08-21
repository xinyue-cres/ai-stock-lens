"""兼容 shim：原 services/scoring_service.py 的 599 行全量搬迁至 services/scan/*。

本文件仅 re-export 原公开接口，外部调用（api/score.py, scripts/*, tests/*）
`from app.services import scoring_service` / `from app.services.scoring_service import ...`
全部不变。
"""
from app.services.scan import (  # noqa: F401
    _build_plan,
    _cache_needs_pull,
    _combined_upsert,
    _is_intraday_now,
    _is_stale,
    _latest_db_dates,
    _load_cached_kline,
    _parse_as_of,
    _run_scan,
    _upsert,
    cancel_scan,
    get_scan_status,
    scan_market,
)
