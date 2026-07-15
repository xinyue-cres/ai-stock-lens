"""历史 K 线字段回填：用 baostock 的权威数据修正历史 turnover / volume / amount / pct_chg。

历史缺失/错位原因：
1. turnover：首次批量同步走了新浪 fallback，新浪不给换手率 → 5798 行 NULL
2. volume：部分老数据（例如 603733）volume 差了 100 倍量级，疑似历史新浪返回值单位与
   当前处理逻辑不一致（后端假设 volume 单位是股，但个别行像是"手"），导致 vol_ratio
   计算失真（新数据是股，旧数据是手，除下来一个 89 倍的量比）

策略：baostock 权威 → 用它的数据覆盖历史所有 K 线字段。turnover NULL 一定补，
其他字段（volume/amount/pct_chg）如与 baostock 相差超过 5% 也覆盖并 log。

用法：
    python -m scripts.backfill_turnover                # 扫全库
    python -m scripts.backfill_turnover --code 600519  # 指定一只
    python -m scripts.backfill_turnover --dry-run      # 试跑不落库
"""
from __future__ import annotations

import argparse
import logging
import re
from datetime import date
from typing import Iterable

from sqlmodel import Session, create_engine, select

from app.config import get_settings
from app.datasource.router import DataRouter, get_data_router
from app.models.kline import KlineDaily

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("backfill_turnover")


# 大盘指数代码（sh000001 等）不是 baostock 支持的股票代码格式，跳过
_STOCK_CODE_RE = re.compile(r"^\d{6}$")


def _codes_with_data(session: Session, only_missing: bool) -> list[str]:
    """列出需回填的股票代码。only_missing=True 只列缺 turnover 的；否则全部股票。"""
    stmt = select(KlineDaily.code)
    if only_missing:
        stmt = stmt.where(KlineDaily.turnover.is_(None))  # type: ignore[union-attr]
    stmt = stmt.distinct()
    codes = [c for c in session.exec(stmt) if _STOCK_CODE_RE.match(c)]
    return sorted(set(codes))


def _all_rows(session: Session, code: str) -> list[KlineDaily]:
    stmt = (
        select(KlineDaily)
        .where(KlineDaily.code == code)
        .order_by(KlineDaily.trade_date)
    )
    return list(session.exec(stmt))


def backfill_one(session: Session, code: str, router: DataRouter, dry_run: bool) -> int:
    rows = _all_rows(session, code)
    if not rows:
        return 0

    start, end = rows[0].trade_date, rows[-1].trade_date
    logger.info("[%s] 本地 %d 行，拉 baostock %s ~ %s", code, len(rows), start, end)
    df = router.fetch_stock_daily_authoritative(code, start, end)
    if df is None or df.empty:
        logger.warning("[%s] baostock 无数据", code)
        return 0

    by_date = {r["trade_date"]: r for _, r in df.iterrows()}

    updated = 0
    for row in rows:
        ref = by_date.get(row.trade_date)
        if ref is None:
            continue

        changed = False
        # turnover：NULL 就补
        ref_turn = ref.get("turnover")
        if row.turnover is None and ref_turn is not None and not _is_nan(ref_turn):
            row.turnover = float(ref_turn)
            changed = True

        # volume：与 baostock 偏差 > 5% 认为脏，覆盖
        ref_vol = ref.get("volume")
        if ref_vol is not None and not _is_nan(ref_vol) and float(ref_vol) > 0:
            local_vol = float(row.volume) if row.volume else 0
            if local_vol == 0 or abs(local_vol - float(ref_vol)) / float(ref_vol) > 0.05:
                logger.info("[%s %s] volume 修正 %s → %s", code, row.trade_date,
                            local_vol, int(ref_vol))
                row.volume = int(ref_vol)
                changed = True

        # amount 同样偏差 > 5% 覆盖
        ref_amt = ref.get("amount")
        if ref_amt is not None and not _is_nan(ref_amt) and float(ref_amt) > 0:
            local_amt = float(row.amount) if row.amount else 0
            if local_amt == 0 or abs(local_amt - float(ref_amt)) / float(ref_amt) > 0.05:
                row.amount = float(ref_amt)
                changed = True

        # pct_chg：0 或缺失才用 baostock 覆盖
        ref_pct = ref.get("pct_chg")
        if ref_pct is not None and not _is_nan(ref_pct):
            local_pct = row.pct_chg or 0.0
            if abs(local_pct) < 0.01 and abs(float(ref_pct)) > 0.01:
                row.pct_chg = float(ref_pct)
                changed = True

        if changed:
            session.add(row)
            updated += 1

    if not dry_run:
        session.commit()
        # analysis_service 缓存指纹是内容 hash，回填改动会自动被检测到；
        # 运行中的其他进程（uvicorn）需要独立观察（不再手动 invalidate，缓存 miss 时自然刷新）
    else:
        session.rollback()
    logger.info("[%s] 修正 %d/%d 行%s", code, updated, len(rows),
                "（dry-run 未落库）" if dry_run else "")
    return updated


def _is_nan(v) -> bool:
    try:
        f = float(v)
        return f != f
    except (TypeError, ValueError):
        return True


def main(codes: Iterable[str] | None, dry_run: bool, all_stocks: bool) -> None:
    settings = get_settings()
    engine = create_engine(settings.db_url)
    router = get_data_router()

    with Session(engine) as session:
        if not codes:
            codes = _codes_with_data(session, only_missing=not all_stocks)
            logger.info("扫描到 %d 只股票: %s", len(codes), list(codes))

        total = 0
        for code in codes:
            try:
                total += backfill_one(session, code, router, dry_run)
            except Exception:
                logger.exception("[%s] 回填失败", code)

        logger.info("完成，总修正 %d 行%s", total, "（dry-run）" if dry_run else "")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--code", action="append", help="指定 code，可重复；默认扫全库")
    ap.add_argument("--dry-run", action="store_true", help="不落库")
    ap.add_argument("--all", action="store_true",
                    help="扫描全部股票（默认只扫缺 turnover 的）")
    args = ap.parse_args()
    main(args.code, args.dry_run, args.all)
