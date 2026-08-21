"""兼容 shim：原 features/stock_scorer.py 的 605 行全量搬迁至 features/scoring/*。

本文件仅 re-export 原公开接口，外部调用（trend_judge, api/score, scripts/, tests/）
`from app.features.stock_scorer import X` 全部不变。
"""
from app.features.scoring import (  # noqa: F401
    _MIN_ROWS,
    _PEAK_CONF_STRONG,
    _PEAK_CONF_STRONG_BY_TF,
    _PEAK_CONF_STRONG_DAILY,
    _PEAK_CONF_STRONG_WEEKLY,
    _PEAK_Z,
    _cycle_stats,
    _golden_continuation,
    _golden_life_score,
    _peak_features,
    _peak_winrate,
    _post_golden_gain,
    _signal_summary,
    compute_indicator_cache,
    score_stock,
    W_BAND,
    W_DIVIDEND,
    W_GOLDEN,
)
from app.features.scoring.base import _norm, _tri  # noqa: F401
