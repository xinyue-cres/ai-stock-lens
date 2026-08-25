"""stock_score.components_json 的 schema 与唯一解析点。

所有对 components_json 的读取都经过这里：字段名/类型校验收口，改 schema 只改一处，
避免散落在 writer / api / scripts 的字符串字面量漂移。

components_json 形状（写入端在 scan/writer._upsert 与 scripts/migrate）：
  {"signal": {...}, "band": {...}, "dividend": {...},
   "trend": {"key_prices": {...}, "indicators": {...}}}
"""
from __future__ import annotations

import json
from typing import Any

from app.models.stock_score import StockScore


def parse(stock_score: StockScore | None) -> dict:
    """解析 components_json；None/空/坏 JSON → 空 dict。唯一解析入口。"""
    if not stock_score or not stock_score.components_json:
        return {}
    try:
        return json.loads(stock_score.components_json) or {}
    except (json.JSONDecodeError, TypeError):
        return {}


def signal_of(stock_score: StockScore | None) -> dict:
    """signal 子树（peak_signal/peak_conf/dif_slope/current_state/hist_* 等）。"""
    return parse(stock_score).get("signal") or {}


def peak_of(stock_score: StockScore | None) -> tuple[str | None, int]:
    """(peak_signal, peak_conf)；缺失返回 (None, 0)。"""
    sig = signal_of(stock_score)
    ps = sig.get("peak_signal")
    conf = sig.get("peak_conf")
    return ps, int(conf) if isinstance(conf, (int, float)) else 0


def pct_b_of(stock_score: StockScore | None) -> float | None:
    """BOLL %B（trend.indicators.pct_b）。"""
    ind = (parse(stock_score).get("trend") or {}).get("indicators") or {}
    v = ind.get("pct_b")
    return float(v) if isinstance(v, (int, float)) else None


def hist_golden_of(weekly_score: StockScore | None) -> tuple[float | None, float | None, float | None]:
    """weekly signal 里的 (hist_peak_pct, hist_peak_median, signal_gain_pct) 三件套。

    用 weekly 而非 daily：weekly 的"金叉周期气质"更稳定，daily bar 太敏感。
    """
    sig = signal_of(weekly_score)
    hp = sig.get("hist_golden_peak_pct")
    hm = sig.get("hist_golden_peak_median")
    sg = sig.get("signal_gain_pct")
    return (
        hp if isinstance(hp, (int, float)) else None,
        hm if isinstance(hm, (int, float)) else None,
        round(sg, 2) if isinstance(sg, (int, float)) else None,
    )


def dist_high_of(daily_score: StockScore | None) -> float | None:
    """距 60 日高的上行空间 %（副参考；主力指标是 hist_golden_*）。"""
    kp = (parse(daily_score).get("trend") or {}).get("key_prices") or {}
    high60 = kp.get("resistance_60d")
    close = kp.get("close")
    if not (isinstance(high60, (int, float)) and high60 and high60 > 0):
        return None
    if not (isinstance(close, (int, float)) and close and close > 0):
        return None
    return round((high60 / close - 1) * 100, 2)


def signal_fields_for_list(stock_score: StockScore | None) -> dict[str, Any]:
    """列表行展示用：从 signal 子树取 dif_slope/dir/current_state/peak_signal/peak_conf。

    _serialize 用——集中字段名，避免 api/utils 里散落字符串。
    """
    sig = signal_of(stock_score)
    return {
        "dif_slope": sig.get("dif_slope"),
        "dif_slope_dir": sig.get("dif_slope_dir"),
        "current_state": sig.get("current_state"),
        "peak_signal": sig.get("peak_signal"),
        "peak_conf": sig.get("peak_conf"),
    }
