"""打分结果写入：StockScore upsert + Combined 合成 upsert。

每条腿（daily/weekly）写完后立刻尝试 combined 合成——双腿齐全时生成 12 档综合结论。
"""
from __future__ import annotations

import json
from datetime import date

from sqlmodel import Session

from app.datasource.base_provider import is_fund_code
from app.models.stock_score import StockScore


def _upsert(session: Session, code: str, name: str, scored: dict, trend: dict,
            scan_date: date, as_of_date: date | None, scope: str,
            timeframe: str = "daily") -> None:
    # 复合主键 (code, scan_timeframe)：daily/weekly 各占一行，互不覆盖
    row = session.get(StockScore, (code, timeframe))
    if row is None:
        row = StockScore(code=code, scan_timeframe=timeframe)
    row.name = name
    row.is_fund = is_fund_code(code)
    row.scan_date = scan_date
    row.scan_scope = scope
    row.as_of_date = as_of_date
    row.total_score = scored["total_score"]
    row.signal_score = scored["signal_score"]
    row.band_score = scored["band_score"]
    row.dividend_score = scored["dividend_score"]
    row.close = scored["close"]
    row.pct_chg = scored["pct_chg"]
    row.turnover = scored["turnover"]
    row.hist_vol = scored["hist_vol"]
    row.adx = scored["adx"]
    row.dividend_yield = scored["dividend_yield"]
    row.trend_stage = trend.get("trend_stage")
    row.can_entry = trend.get("can_entry")
    row.entry_reason = trend.get("entry_reason")
    row.components_json = json.dumps({
        **scored["components"],
        "trend": {"key_prices": trend.get("key_prices"), "indicators": trend.get("indicators")},
    }, ensure_ascii=False)
    session.add(row)
    session.commit()
    # 关键：每条腿写完后立刻尝试合并评判（需要 daily+weekly 双方都存在才有意义）
    _combined_upsert(session, code, name, scan_date, scope)


def _combined_upsert(session: Session, code: str, name: str,
                     scan_date: date, scope: str | None) -> None:
    """根据 stock_score 的 daily+weekly 两条腿计算 combined 结论并 upsert。

    只有当两个 timeframe 都有当日扫描结果时才计算；否则只更新已经有的行。
    """
    from app.features.combined_judge import (
        combined_entry_reason,
        combined_meta,
        combined_score,
        combined_stage,
    )
    from app.models.stock_score_combined import StockScoreCombined

    daily_row = session.get(StockScore, (code, "daily"))
    weekly_row = session.get(StockScore, (code, "weekly"))
    if daily_row is None and weekly_row is None:
        return  # 一条腿都没，不算

    w_total = weekly_row.total_score if weekly_row else 0.0
    d_total = daily_row.total_score if daily_row else 0.0
    w_stage = weekly_row.trend_stage if weekly_row else "insufficient"
    d_stage = daily_row.trend_stage if daily_row else "insufficient"

    def _load_comp(r) -> dict:
        """解析 components_json，出错返回空 dict。单一解析点（P2-2）。"""
        if not r or not r.components_json:
            return {}
        try:
            return json.loads(r.components_json) or {}
        except (json.JSONDecodeError, TypeError):
            return {}

    def _peak_of(r) -> tuple[str | None, int]:
        sig = (_load_comp(r).get("signal") or {})
        ps = sig.get("peak_signal")
        conf = sig.get("peak_conf")
        return ps, int(conf) if isinstance(conf, (int, float)) else 0

    def _pct_b_of(r) -> float | None:
        """从 components_json 提取 BOLL pct_b（trend.indicators.pct_b）。"""
        ind = (_load_comp(r).get("trend") or {}).get("indicators") or {}
        v = ind.get("pct_b")
        return float(v) if isinstance(v, (int, float)) else None

    def _hist_from(weekly_r) -> tuple[float | None, float | None, float | None]:
        """weekly signal_summary 里的 hist 三件套（golden peak mean/median + signal_gain）。

        用 weekly 而非 daily：weekly 的"金叉周期气质"更稳定，daily bar 太敏感。
        """
        sig = (_load_comp(weekly_r).get("signal") or {})
        hp = sig.get("hist_golden_peak_pct")
        hm = sig.get("hist_golden_peak_median")
        sg = sig.get("signal_gain_pct")
        return (
            hp if isinstance(hp, (int, float)) else None,
            hm if isinstance(hm, (int, float)) else None,
            round(sg, 2) if isinstance(sg, (int, float)) else None,
        )

    def _dist_high_of(daily_r) -> float | None:
        """距 60 日高的上行空间 %（副参考；主力指标是 hist_golden_*）。"""
        kp = (_load_comp(daily_r).get("trend") or {}).get("key_prices") or {}
        high60 = kp.get("resistance_60d")
        close = kp.get("close")
        if not (isinstance(high60, (int, float)) and high60 and high60 > 0):
            return None
        if not (isinstance(close, (int, float)) and close and close > 0):
            return None
        return round((high60 / close - 1) * 100, 2)

    w_peak, w_conf = _peak_of(weekly_row)
    d_peak, d_conf = _peak_of(daily_row)
    w_pct_b = _pct_b_of(weekly_row)
    d_pct_b = _pct_b_of(daily_row)

    stage = combined_stage(w_stage, d_stage)

    # 入场时机不优约束：BOLL pct_b >= 0.8 时 strong_buy 降级到 buy。
    # 历史数据（100 只票×59509 时点 fwd 5 日收益）：pct_b 0.5-0.8 中位 +0.08%，
    # 0.8-0.95 中位 -0.14%（已短期转负）；强买档必须更严。
    # 只 applied 到 strong_buy，不 cascaded 整条 trend_judge 决策。
    demote_reason: str | None = None
    if stage == "strong_buy":
        worst_pct_b = max((p for p in (w_pct_b, d_pct_b) if p is not None), default=None)
        if worst_pct_b is not None and worst_pct_b >= 0.8:
            stage = "buy"
            demote_reason = f"BOLL 贴上轨 {worst_pct_b:.0%}（超过 sweet spot 80%），入场时机已不优——降级 strong_buy → buy"
    total = combined_score(w_total, d_total, stage)
    meta = combined_meta(stage)
    can_entry = stage in ("strong_buy", "buy", "light_buy", "deep_pullback_entry")
    entry_reason = combined_entry_reason(
        stage,
        {"total_score": w_total, "signal_score": weekly_row.signal_score if weekly_row else None,
         "trend_stage": w_stage, "peak_signal": w_peak, "peak_conf": w_conf},
        {"total_score": d_total, "signal_score": daily_row.signal_score if daily_row else None,
         "trend_stage": d_stage, "peak_signal": d_peak, "peak_conf": d_conf},
    )

    row = session.get(StockScoreCombined, code)
    if row is None:
        row = StockScoreCombined(code=code)
    row.name = name
    row.is_fund = is_fund_code(code)
    row.scan_date = scan_date
    row.scan_scope = scope
    row.weekly_total = w_total
    row.weekly_signal = weekly_row.signal_score if weekly_row else None
    row.weekly_stage = w_stage
    row.weekly_peak_signal = w_peak
    row.weekly_peak_conf = w_conf
    row.daily_total = d_total
    row.daily_signal = daily_row.signal_score if daily_row else None
    row.daily_stage = d_stage
    row.daily_peak_signal = d_peak
    row.daily_peak_conf = d_conf
    row.combined_score = total
    row.combined_stage = stage
    row.can_entry = can_entry
    row.entry_reason = entry_reason
    row.trade_hint = meta.get("trade_hint")
    row.demote_reason = demote_reason
    # 空间（保留 dist_high 兼容）：距 60 日高 = 旧逻辑。
    # 主力指标改该股历史金叉 peak（mean + median）—— 比 60 日高更能代表"这次能涨多少"。
    hist_golden_peak_pct, hist_golden_peak_median, weekly_signal_gain_pct = _hist_from(weekly_row)
    space_pct = _dist_high_of(daily_row)
    row.space_pct = space_pct
    row.hist_golden_peak_pct = hist_golden_peak_pct
    row.hist_golden_peak_median = hist_golden_peak_median
    row.weekly_signal_gain_pct = weekly_signal_gain_pct
    # as_of_date 用两条腿中较新的一个
    candidates = [r.as_of_date for r in (daily_row, weekly_row) if r and r.as_of_date]
    row.as_of_date = max(candidates) if candidates else None
    session.add(row)
    session.commit()
