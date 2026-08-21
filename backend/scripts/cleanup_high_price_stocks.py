"""清理 DB 中股价 >100 元的股票：stock / stock_score / stock_score_combined / kline_daily / ai_report 五表级联删除。

用于 v1.2.1 一次性清理（2026-08-21），执行后删除 15 只 >100 元票

（茅台 1291.5 / 寒武纪 1010.88 / 新易盛 414.02 / 吉比特 393.91 / 兆易创新 403.5）
及关联 K 线 18,262 行、AI 报告 31 条、打分行 30+15 条。

保留脚本：同类型数据量再继续上涨时（如 >150）可提参数化重跑。
"""
from __future__ import annotations

import argparse

from sqlalchemy import text

from app.db import engine

TABLES = [
    ("ai_report", "DELETE FROM ai_report WHERE code=:c"),
    ("stock_score_combined", "DELETE FROM stock_score_combined WHERE code=:c"),
    ("stock_score", "DELETE FROM stock_score WHERE code=:c"),
    ("kline_daily", "DELETE FROM kline_daily WHERE code=:c"),
    ("stock", "DELETE FROM stock WHERE code=:c"),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=100.0, help="股价阈值（元）")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写")
    args = parser.parse_args()
    threshold = args.threshold

    with engine.begin() as conn:
        # 找 >threshold 的 code（从 stock_score.close 判断，最准确的当前收盘参考）
        rows = conn.execute(
            text("SELECT DISTINCT code FROM stock_score WHERE close > :t"),
            {"t": threshold},
        ).all()
        codes = [r[0] for r in rows]
        print(f"共 {len(codes)} 只股票 >{threshold} 元")
        for c in codes:
            print(f"  {c}")

        if args.dry_run:
            # dry run：只查出数量不进制删
            for code in codes:
                for table, sql in TABLES:
                    n = conn.execute(
                        text(f"SELECT COUNT(*) FROM {table} WHERE code=:c"), {"c": code}
                    ).scalar()
                    if n:
                        print(f"  DRY {code} {table}: {n} rows")
            return

        # 实际删（按依赖序）
        for code in codes:
            for table, sql in TABLES:
                r = conn.execute(text(sql), {"c": code})
                if r.rowcount:
                    print(f"  {code} {table}: -{r.rowcount}")
    print("完成")


if __name__ == "__main__":
    main()
