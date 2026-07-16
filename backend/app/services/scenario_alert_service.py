"""Scenario 命中检测：每日收盘后检查 AI 报告预案是否被当日 K 线触发。"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from typing import Any

from sqlmodel import Session, select

from app.models.ai_report import AIReport
from app.models.kline import KlineDaily
from app.models.scenario_alert import ScenarioAlert
from app.models.stock import Stock

logger = logging.getLogger(__name__)

_HORIZONS = ["combined", "anti_quant", "reflexivity"]


def _eval_condition(cond: dict[str, Any], bar: KlineDaily, vol_ratio: float | None) -> bool:
    kind = cond.get("kind")
    op = cond.get("op")
    val = cond.get("value")
    if op not in (">=", "<=") or val is None:
        return False
    try:
        target = float(val)
    except (TypeError, ValueError):
        return False

    if kind == "price":
        which = cond.get("target") or "close"
        actual = {"close": bar.close, "high": bar.high, "low": bar.low}.get(which)
        if actual is None:
            return False
        return actual >= target if op == ">=" else actual <= target

    if kind == "volume_ratio":
        if vol_ratio is None:
            return False
        return vol_ratio >= target if op == ">=" else vol_ratio <= target

    return False


def _compute_volume_ratio(session: Session, code: str, trade_date: date) -> float | None:
    """当日量 / 前 5 日均量。"""
    rows = session.exec(
        select(KlineDaily)
        .where(KlineDaily.code == code, KlineDaily.trade_date <= trade_date)
        .order_by(KlineDaily.trade_date.desc())
        .limit(6)
    ).all()
    if len(rows) < 2:
        return None
    today_vol = rows[0].volume
    prev_vols = [r.volume for r in rows[1:6]]
    if not prev_vols:
        return None
    avg = sum(prev_vols) / len(prev_vols)
    if avg <= 0:
        return None
    return today_vol / avg


def check_scenarios_for_stock(
    session: Session, code: str, trade_date: date, model: str
) -> list[ScenarioAlert]:
    """检查一只股票所有 horizon 最新报告的 scenarios 是否在 trade_date 命中。"""
    bar = session.exec(
        select(KlineDaily).where(KlineDaily.code == code, KlineDaily.trade_date == trade_date)
    ).first()
    if not bar:
        return []

    vol_ratio = _compute_volume_ratio(session, code, trade_date)
    alerts: list[ScenarioAlert] = []

    for horizon in _HORIZONS:
        report = session.exec(
            select(AIReport)
            .where(AIReport.code == code, AIReport.model == model, AIReport.horizon == horizon)
            .order_by(AIReport.as_of_date.desc(), AIReport.created_at.desc())
            .limit(1)
        ).first()
        if not report or not report.extras_json:
            continue
        # 报告数据日期必须早于或等于 trade_date（不检查未来数据对应的报告）
        if report.as_of_date > trade_date:
            continue

        try:
            extras = json.loads(report.extras_json)
        except json.JSONDecodeError:
            continue

        scenarios = extras.get("scenarios") or []
        for idx, sc in enumerate(scenarios):
            if not isinstance(sc, dict):
                continue
            conditions = sc.get("conditions") or []
            if not conditions:
                continue

            # 检查是否已存在
            existing = session.exec(
                select(ScenarioAlert).where(
                    ScenarioAlert.code == code,
                    ScenarioAlert.report_id == report.id,
                    ScenarioAlert.scenario_index == idx,
                    ScenarioAlert.triggered_date == trade_date,
                )
            ).first()
            if existing:
                continue

            # 所有条件 AND 判定
            all_met = all(_eval_condition(c, bar, vol_ratio) for c in conditions)
            if not all_met:
                continue

            alert = ScenarioAlert(
                code=code,
                report_id=report.id,  # type: ignore[arg-type]
                horizon=horizon,
                scenario_index=idx,
                trigger=sc.get("trigger") or "",
                direction=sc.get("direction") or "neutral",
                triggered_date=trade_date,
            )
            session.add(alert)
            alerts.append(alert)

    if alerts:
        session.commit()
        for a in alerts:
            session.refresh(a)
    return alerts


def check_all_watchlist(session: Session, trade_date: date | None = None) -> int:
    """扫描全部自选股，检查 scenario 命中。返回新增 alert 数。"""
    from app.ai.client import get_model_name

    if trade_date is None:
        # 取最近一个交易日
        latest = session.exec(
            select(KlineDaily.trade_date).order_by(KlineDaily.trade_date.desc()).limit(1)
        ).first()
        if not latest:
            return 0
        trade_date = latest

    model = get_model_name()
    stocks = list(session.exec(select(Stock).where(Stock.is_watchlist == True)))  # noqa: E712
    total = 0
    for stock in stocks:
        try:
            alerts = check_scenarios_for_stock(session, stock.code, trade_date, model)
            total += len(alerts)
        except Exception:
            logger.exception("scenario check failed for %s", stock.code)
    logger.info("Scenario 检测完成 · %d 只股 · 新增 %d 条 alert", len(stocks), total)
    return total


def get_active_alerts(
    session: Session, codes: list[str], days: int = 3
) -> dict[str, list[dict]]:
    """获取近 N 天内的 triggered alerts，按 code 分组。"""
    cutoff = date.today() - timedelta(days=days)
    rows = session.exec(
        select(ScenarioAlert)
        .where(ScenarioAlert.code.in_(codes), ScenarioAlert.triggered_date >= cutoff)  # type: ignore[arg-type]
        .order_by(ScenarioAlert.triggered_date.desc())
    ).all()

    result: dict[str, list[dict]] = {}
    for r in rows:
        entry = {
            "horizon": r.horizon,
            "trigger": r.trigger,
            "direction": r.direction,
            "triggered_date": r.triggered_date.isoformat(),
        }
        result.setdefault(r.code, []).append(entry)
    return result
