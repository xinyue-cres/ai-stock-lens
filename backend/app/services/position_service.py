"""持仓服务：CRUD + 用最新收盘价算浮盈。"""
from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Session, select

from app.models.ai_report import AIReport
from app.models.kline import KlineDaily
from app.models.position import Position
from app.models.stock import Stock


def get_position(session: Session, code: str) -> Position | None:
    return session.exec(select(Position).where(Position.code == code)).first()


def list_positions(session: Session) -> list[Position]:
    return list(session.exec(select(Position).order_by(Position.updated_at.desc())))


def upsert_position(
    session: Session,
    code: str,
    quantity: int,
    cost_price: float,
    opened_at: date,
    note: str | None = None,
) -> Position:
    existing = get_position(session, code)
    now = datetime.now()
    if existing:
        existing.quantity = quantity
        existing.cost_price = cost_price
        existing.opened_at = opened_at
        existing.note = note
        existing.updated_at = now
        session.add(existing)
        session.commit()
        session.refresh(existing)
        return existing
    pos = Position(
        code=code,
        quantity=quantity,
        cost_price=cost_price,
        opened_at=opened_at,
        note=note,
        updated_at=now,
    )
    session.add(pos)
    session.commit()
    session.refresh(pos)
    return pos


def delete_position(session: Session, code: str) -> bool:
    p = get_position(session, code)
    if not p:
        return False
    session.delete(p)
    session.commit()
    return True


def _last_two_closes(session: Session, code: str) -> tuple[float | None, float | None]:
    """返回 (最新收盘, 前一根收盘)，用于算今日浮盈。"""
    rows = session.exec(
        select(KlineDaily.close)
        .where(KlineDaily.code == code)
        .order_by(KlineDaily.trade_date.desc())
        .limit(2)
    ).all()
    if not rows:
        return (None, None)
    latest = float(rows[0]) if rows[0] is not None else None
    prev = float(rows[1]) if len(rows) > 1 and rows[1] is not None else None
    return (latest, prev)


def _latest_verdict(session: Session, code: str) -> str | None:
    """取该 code 最近一份 combined AI 报告的 verdict。"""
    row = session.exec(
        select(AIReport.verdict)
        .where(AIReport.code == code, AIReport.horizon == "combined")
        .order_by(AIReport.as_of_date.desc(), AIReport.created_at.desc())
        .limit(1)
    ).first()
    return row


def _stock_name(session: Session, code: str) -> str | None:
    stock = session.get(Stock, code)
    return stock.name if stock else None


def summarize(session: Session, position: Position) -> dict:
    """浮盈快照（用最新收盘价近似，非实时）+ 今日浮盈 + AI verdict + 持有天数 + 股票名。"""
    latest, prev = _last_two_closes(session, position.code)
    pnl_pct = None
    market_value = None
    today_pnl = None
    today_pnl_pct = None
    if latest is not None and position.cost_price > 0 and position.quantity > 0:
        pnl_pct = (latest - position.cost_price) / position.cost_price
        market_value = latest * position.quantity
    if latest is not None and prev is not None and prev > 0 and position.quantity > 0:
        today_pnl = (latest - prev) * position.quantity
        today_pnl_pct = (latest - prev) / prev

    hold_days = (date.today() - position.opened_at).days

    return {
        "code": position.code,
        "name": _stock_name(session, position.code),
        "quantity": position.quantity,
        "cost_price": position.cost_price,
        "opened_at": position.opened_at.isoformat(),
        "note": position.note,
        "latest_close": latest,
        "unrealized_pnl_pct": pnl_pct,
        "market_value": market_value,
        "today_pnl": today_pnl,
        "today_pnl_pct": today_pnl_pct,
        "verdict": _latest_verdict(session, position.code),
        "hold_days": hold_days,
        "updated_at": position.updated_at.isoformat() + "Z",
    }


def get_positions_by_codes(session: Session, codes: list[str]) -> dict[str, Position]:
    """一次拉多个 code 的持仓，watchlist 列表用。"""
    if not codes:
        return {}
    rows = session.exec(select(Position).where(Position.code.in_(codes)))  # type: ignore[attr-defined]
    return {p.code: p for p in rows}
