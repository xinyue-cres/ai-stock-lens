"""打分引擎包：按职责拆为 rates / base / golden / peak / band / engine 六个模块。

对外公开接口与原 features/stock_scorer.py 完全一致：
- score_stock / compute_indicator_cache                      打分 + 指标缓存
- _PEAK_CONF_STRONG / _PEAK_CONF_STRONG_BY_TF               过峰置信度阈值
- _post_golden_gain / _golden_life_score / _golden_continuation  金叉延续性
- _peak_features / _cycle_stats / _peak_winrate / _signal_summary  周期/过峰统计
"""
from .engine import compute_indicator_cache, score_stock  # noqa: F401
from .golden import (  # noqa: F401
    _cycle_stats,
    _golden_continuation,
    _golden_life_score,
    _peak_winrate,
    _post_golden_gain,
    _signal_summary,
)
from .peak import _peak_features  # noqa: F401
from .rates import (  # noqa: F401
    _MIN_ROWS,
    _PEAK_CONF_STRONG,
    _PEAK_CONF_STRONG_BY_TF,
    _PEAK_CONF_STRONG_DAILY,
    _PEAK_CONF_STRONG_WEEKLY,
    _PEAK_Z,
    W_BAND,
    W_DIVIDEND,
    W_GOLDEN,
)
