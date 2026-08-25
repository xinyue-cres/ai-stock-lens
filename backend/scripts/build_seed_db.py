"""构建打包用的种子数据库 seed.sqlite（仅 stock 元数据表，无 K 线/无自选）。

在 CI 打包前运行：拉一次全 A + ETF + LOF 列表（code 已清洗 6 位），
写进独立 SQLite 文件，随 exe 打进包里。用户首次启动时若 data/app.db
不存在，直接从 seed 复制——首搜零等待，不用现场拉 20s 远程列表。

种子数据会随构建时间过时（新股/改名）——由 search_stocks 的远程兜底
自然补齐，兜底逻辑仍在。

用法：
    cd backend && python scripts/build_seed_db.py
    产物：backend/seed.sqlite（约几百 KB）
"""
from __future__ import annotations

import sys
from pathlib import Path

# CI（GitHub Windows runner）stdout 默认 cp1252 编码，print 中文直接 UnicodeEncodeError。
# 强制 UTF-8 + replace 兜底：任何环境（本地 GBK 控制台 / CI cp1252）都不会因日志炸掉。
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, SQLModel, create_engine

from app.models.stock import Stock  # noqa: F401  (register table)
from app.services.stock_service import refresh_stock_index

SEED_PATH = Path(__file__).resolve().parent.parent / "seed.sqlite"


def main() -> None:
    if SEED_PATH.exists():
        SEED_PATH.unlink()
    seed_engine = create_engine(f"sqlite:///{SEED_PATH}")
    SQLModel.metadata.create_all(seed_engine)
    with Session(seed_engine) as s:
        added = refresh_stock_index(s)
    print(f"种子库已生成: {SEED_PATH}（stock 表 {added} 条，仅元数据）")


if __name__ == "__main__":
    main()
