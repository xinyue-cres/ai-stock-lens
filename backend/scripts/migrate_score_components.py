"""用本地 K 线缓存重算 stock_score 的打分/趋势字段（不发起任何网络请求）。

用途：
- 算法升级（边界修复 / 参数调整）后，让 DB 里的老行刷新为新算法的输出
- 替代"全量网络重扫"（耗时长、外部依赖不可控）

处理流程：
  for each (code, timeframe) in stock_score:
      daily_df = kline_daily[code]        (本地)
      bars     = to_bars(daily_df, timeframe)
      cache    = compute_indicator_cache(bars)
      scored   = score_stock(bars, div_yield, is_fund, cache=cache, timeframe=timeframe)
      trend    = judge_trend(bars, signal_score=scored[signal_score], cache=cache)
      更新 stock_score（保留 code+scan_timeframe 复合 PK）

使用：
  source .venv/bin/activate
  python scripts/migrate_score_components.py                     # 全部 timeframe 都跑
  python scripts/migrate_score_components.py --timeframe daily   # 只 daily
  python scripts/migrate_score_components.py --dry-run           # 只打印不写

性能：1000 只 × 0.5s ≈ 8 分钟（SQLite 单 Session 串行 + GIL 下 compute）
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# 脚本直接执行时定位 backend 包根（scripts/<file>.py 上一级）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from app.config import get_settings
from app.db import engine
from app.datasource.base_provider import is_fund_code
from app.features.stock_scorer import compute_indicator_cache, score_stock
from app.features.timeframe import Timeframe, to_bars
from app.features.trend_judge import judge_trend
from app.models.stock_score import StockScore
from app.services.dividend_service import load_dividend_map
from app.services.scoring_service import _load_cached_kline, _parse_as_of

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("migrate")


def migrate_one(s: Session, code: str, name: str, timeframe: Timeframe,
                settings, start: date, end: date,
                dividend_map: dict[str, float | None], dry_run: bool) -> tuple[bool, str]:
    """重算单只 (code, timeframe)，写入 stock_score。返回 (是否更新, 备注)。"""
    df = _load_cached_kline(s, code, start, min_bars=100)
    if df is None or df.empty or len(df) < 60:
        return False, "缓存不足 <60 bar，跳过（_MIN_ROWS 规则）"
    bars = to_bars(df, timeframe)
    if len(bars) < 60:
        return False, f"resample 后 K 线不足 60 bar（{len(bars)})"
    cache = compute_indicator_cache(bars)
    div_yield = dividend_map.get(code)
    scored = score_stock(bars, div_yield, is_fund_code(code), cache=cache, timeframe=timeframe)
    if scored is None:
        return False, "score_stock 返回 None"
    trend = judge_trend(bars, signal_score=scored["signal_score"], cache=cache)
    as_of = _parse_as_of(bars["trade_date"].iloc[-1])

    if dry_run:
        return True, f"dry: total={scored['total_score']:.1f} stage={trend['trend_stage']}"

    row = s.get(StockScore, (code, timeframe))
    if row is None:
        row = StockScore(code=code, scan_timeframe=timeframe)
    row.name = name
    row.is_fund = is_fund_code(code)
    # scan_date/scan_scope 保留原值（这是历史扫描的标记，不应被覆盖）
    row.as_of_date = as_of
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
    s.add(row)
    return True, "ok"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeframe", choices=["daily", "weekly"], default=None,
                        help="只迁移某个周期；默认两个都跑")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写库")
    parser.add_argument("--codes", type=str, default=None, help="只迁移指定 code（逗号分隔）")
    args = parser.parse_args()

    settings = get_settings()
    end = date.today()
    start = end - timedelta(days=settings.scan_kline_days * 2)  # 留 buffer 给 weekly resample

    with Session(engine) as s:
        # 找出要迁移的 (code, timeframe) 对
        stmt = select(StockScore.code, StockScore.name, StockScore.scan_timeframe)
        if args.timeframe:
            stmt = stmt.where(StockScore.scan_timeframe == args.timeframe)
        if args.codes:
            codes = [c.strip() for c in args.codes.split(",") if c.strip()]
            stmt = stmt.where(StockScore.code.in_(codes))  # type: ignore[attr-defined]
        rows = list(s.exec(stmt).all())

    logger.info("待迁移 %d 行", len(rows))

    code_set = sorted({r[0] for r in rows})
    with Session(engine) as s:
        dividend_map = load_dividend_map(s, code_set)

    ok_count = 0
    skip_count = 0
    fail_count = 0
    with Session(engine) as s:
        for i, (code, name, tf) in enumerate(rows):
            try:
                ok, note = migrate_one(s, code, name, tf, settings, start, end, dividend_map, args.dry_run)
                if ok:
                    ok_count += 1
                    if i < 5 or (i + 1) % 200 == 0:
                        logger.info("[%d/%d] %s/%s %s", i + 1, len(rows), code, tf, note)
                else:
                    skip_count += 1
                    if skip_count <= 5:
                        logger.info("[%d/%d] %s/%s 跳过： %s", i + 1, len(rows), code, tf, note)
            except Exception as e:  # noqa: BLE001
                fail_count += 1
                if fail_count <= 5:
                    logger.exception("[%d/%d] %s/%s 失败： %s", i + 1, len(rows), code, tf, e)
        if not args.dry_run:
            s.commit()

    logger.info("完成： ok=%d skip=%d fail=%d (dry-run=%s)", ok_count, skip_count, fail_count, args.dry_run)


if __name__ == "__main__":
    main()
