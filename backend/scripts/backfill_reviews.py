"""一次性回填历史 AI 报告的复盘记录。

用法：
    cd backend && python -m scripts.backfill_reviews
"""
from __future__ import annotations

import logging

from sqlmodel import Session

from app.db import engine, init_db
from app.services.review_service import review_all_pending


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    init_db()
    with Session(engine) as session:
        stats = review_all_pending(session)
    print(f"完成 · 报告数 {stats['reports']} · 新增复盘 {stats['new_reviews']}")


if __name__ == "__main__":
    main()
