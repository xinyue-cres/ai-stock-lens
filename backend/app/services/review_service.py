"""复盘引擎：对给定 AIReport，在其后续交易日机械评估 scenarios 命中与 verdict 正确性。

设计：
  - 命中判定基于 scenarios[*].conditions（结构化 AND 语义），无 conditions 的 scenario 记录为 pending。
  - 量比 = 当日成交量 / 前 5 日均量。
  - verdict_hit：短线报告用 T+1~T+3 累计涨跌幅判定，中线用 T+1~T+10，综合视角同中线。
      bullish/bearish 阈值 ±2%；|Δ|<2% 记 miss（对牛熊而言）/hit（对 neutral 而言）；caution 视为看跌 miss。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from sqlmodel import Session, select

from app.models.ai_report import AIReport
from app.models.ai_report_review import AIReportReview
from app.models.kline import KlineDaily

logger = logging.getLogger(__name__)


_HORIZON_WINDOW = {"short": 3, "medium": 10, "combined": 10}
_VERDICT_THRESHOLD_PCT = 2.0


@dataclass
class _Bar:
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int


def _load_bars(session: Session, code: str, start: date) -> list[_Bar]:
    """加载 as_of_date 及之后的所有 K 线（含 as_of_date 本身作为基准）。"""
    rows = session.exec(
        select(KlineDaily).where(KlineDaily.code == code, KlineDaily.trade_date >= start).order_by(KlineDaily.trade_date)
    ).all()
    return [
        _Bar(
            trade_date=r.trade_date,
            open=r.open,
            high=r.high,
            low=r.low,
            close=r.close,
            volume=r.volume,
        )
        for r in rows
    ]


def _volume_ratio(bars: list[_Bar], idx: int) -> float | None:
    """当日量 / 前 5 日均量。前 5 日不足则返回 None。"""
    if idx < 5:
        return None
    prev = bars[idx - 5 : idx]
    if not prev:
        return None
    avg = sum(b.volume for b in prev) / len(prev)
    if avg <= 0:
        return None
    return bars[idx].volume / avg


def _op_ok(actual: float, op: str, target: float) -> bool:
    if op == ">=":
        return actual >= target
    if op == "<=":
        return actual <= target
    return False


def _eval_condition(cond: dict[str, Any], bar: _Bar, vol_ratio: float | None) -> tuple[bool, float | None]:
    """返回 (是否满足, 实际值)。字段无效则 (False, None)。"""
    kind = cond.get("kind")
    op = cond.get("op")
    val = cond.get("value")
    if op not in (">=", "<=") or val is None:
        return False, None
    try:
        target = float(val)
    except (TypeError, ValueError):
        return False, None
    if kind == "price":
        which = cond.get("target") or "close"
        actual = {"close": bar.close, "high": bar.high, "low": bar.low}.get(which)
        if actual is None:
            return False, None
        return _op_ok(actual, op, target), actual
    if kind == "volume_ratio":
        if vol_ratio is None:
            return False, None
        return _op_ok(vol_ratio, op, target), vol_ratio
    return False, None


def _eval_scenarios(report: AIReport, bar: _Bar, vol_ratio: float | None) -> tuple[list[dict[str, Any]], int, int]:
    """返回 (每个 scenario 的评估细节, 命中数, 有 conditions 的总数)。"""
    if not report.extras_json:
        return [], 0, 0
    try:
        extras = json.loads(report.extras_json)
    except json.JSONDecodeError:
        return [], 0, 0
    scenarios = extras.get("scenarios") or []
    results: list[dict[str, Any]] = []
    triggered = 0
    total_with_cond = 0
    for i, sc in enumerate(scenarios):
        if not isinstance(sc, dict):
            continue
        conds = sc.get("conditions") or []
        if not conds:
            results.append(
                {
                    "index": i,
                    "direction": sc.get("direction"),
                    "trigger": sc.get("trigger"),
                    "triggered": None,
                    "condition_results": [],
                }
            )
            continue
        total_with_cond += 1
        cond_results = []
        all_ok = True
        for c in conds:
            ok, actual = _eval_condition(c, bar, vol_ratio)
            cond_results.append(
                {
                    "kind": c.get("kind"),
                    "op": c.get("op"),
                    "value": c.get("value"),
                    "target": c.get("target"),
                    "actual": actual,
                    "ok": ok,
                }
            )
            if not ok:
                all_ok = False
        if all_ok:
            triggered += 1
        results.append(
            {
                "index": i,
                "direction": sc.get("direction"),
                "trigger": sc.get("trigger"),
                "triggered": all_ok,
                "condition_results": cond_results,
            }
        )
    return results, triggered, total_with_cond


def _judge_verdict(report: AIReport, bars: list[_Bar], base_idx: int, cur_idx: int) -> tuple[str, float]:
    """从 base（as_of_date）到 cur 的累计涨跌幅评估 verdict 正确性。

    返回 (hit|miss|pending, 累计涨跌幅%)。
    仅当天数达到 horizon 对应窗口时给 hit/miss，否则 pending。
    """
    base_close = bars[base_idx].close
    cur_close = bars[cur_idx].close
    if base_close <= 0:
        return "pending", 0.0
    pct = (cur_close - base_close) / base_close * 100
    window = _HORIZON_WINDOW.get(report.horizon, 10)
    days_after = cur_idx - base_idx
    if days_after < window:
        return "pending", pct
    v = report.verdict
    thr = _VERDICT_THRESHOLD_PCT
    if v == "bullish":
        return ("hit" if pct >= thr else "miss"), pct
    if v == "bearish" or v == "caution":
        return ("hit" if pct <= -thr else "miss"), pct
    if v == "neutral":
        return ("hit" if abs(pct) < thr else "miss"), pct
    return "n/a", pct


def review_report(session: Session, report: AIReport, up_to: date | None = None) -> list[AIReportReview]:
    """对一份 report 从 T+1 起补齐至今（或 up_to）的复盘记录，返回新增/已存在的复盘条目。

    幂等：已存在 (report_id, review_date) 会跳过。
    """
    bars = _load_bars(session, report.code, report.as_of_date)
    if len(bars) < 2:
        return []
    # 确认 bars[0] 就是 as_of_date；某些情况下 as_of_date 非交易日
    base_idx = 0
    if bars[0].trade_date != report.as_of_date:
        # 找到 as_of_date 或之后第一根 bar 作为基准
        base_idx = 0

    existing_dates = set(
        session.exec(
            select(AIReportReview.review_date).where(AIReportReview.report_id == report.id)
        ).all()
    )

    created: list[AIReportReview] = []
    horizon_window = _HORIZON_WINDOW.get(report.horizon, 10)

    for cur_idx in range(base_idx + 1, len(bars)):
        bar = bars[cur_idx]
        if up_to and bar.trade_date > up_to:
            break
        if bar.trade_date in existing_dates:
            continue
        days_after = cur_idx - base_idx

        vol_ratio = _volume_ratio(bars, cur_idx)
        scenarios_eval, triggered, total_cond = _eval_scenarios(report, bar, vol_ratio)
        verdict_hit, pct = _judge_verdict(report, bars, base_idx, cur_idx)

        notes_bits = [
            f"T+{days_after} {bar.trade_date.isoformat()} 收 {bar.close:.2f} ({pct:+.2f}%)"
        ]
        if total_cond > 0:
            notes_bits.append(f"命中 scenario {triggered}/{total_cond}")
        if verdict_hit != "pending":
            notes_bits.append(f"verdict {report.verdict} → {verdict_hit}")

        row = AIReportReview(
            report_id=report.id,  # type: ignore[arg-type]
            code=report.code,
            as_of_date=report.as_of_date,
            review_date=bar.trade_date,
            days_after=days_after,
            verdict_hit=verdict_hit,
            price_change_pct=pct,
            scenarios_json=json.dumps(scenarios_eval, ensure_ascii=False) if scenarios_eval else None,
            triggered_count=triggered,
            total_scenarios=total_cond,
            notes=" · ".join(notes_bits),
        )
        session.add(row)
        created.append(row)

        # 只跑到 horizon 窗口之后一天就够了（继续跑意义不大）
        if days_after >= horizon_window + 2:
            break

    if created:
        session.commit()
        for r in created:
            session.refresh(r)
    return created


def review_all_pending(session: Session, up_to: date | None = None) -> dict[str, int]:
    """扫描所有 report，为每一份补齐复盘。返回 {报告数, 新增复盘行数}。"""
    reports = session.exec(select(AIReport).order_by(AIReport.as_of_date)).all()
    total_new = 0
    for rep in reports:
        try:
            created = review_report(session, rep, up_to=up_to)
            total_new += len(created)
        except Exception:
            logger.exception("复盘失败 report_id=%s code=%s", rep.id, rep.code)
    return {"reports": len(reports), "new_reviews": total_new}
