"""数据库引擎、Session 与初始化编排。

- engine / get_session：引擎与请求级 Session（API 层 Depends 用）
- init_db：启动期编排——seed 复制 → 模型迁移 → create_all
- 历史 schema 迁移见 .migrations，种子复制见 .seed

调用方保持 `from app.db import engine, get_session, init_db` 不变。
"""
from __future__ import annotations

import logging

from sqlalchemy import event, text
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

logger = logging.getLogger(__name__)

_settings = get_settings()

engine = create_engine(
    _settings.db_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _connection_record) -> None:
    """SQLite 并发优化：
    - WAL：读写可并发（选股扫描 8 worker 并发写 K 线/打分，前端同时读列表不互斥）
    - busy_timeout=30s：写锁冲突时等待而非立刻抛 "database is locked"（默认 5s 太短）
    """
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.close()


def get_session():
    """请求级 Session 生成器（FastAPI Depends 用）。"""
    with Session(engine) as session:
        yield session


def _migrate_add_column(table: str, column: str, ddl: str) -> None:
    """幂等的 ALTER TABLE ADD COLUMN（SQLite 简单迁移）。"""
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).all()
        existing = {r[1] for r in rows}
        if column not in existing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            conn.commit()


def _migrate_drop_column(table: str, column: str) -> None:
    """删除模型已移除的表冗余列（SQLite 3.35+ 支持 DROP COLUMN）。

    例：stock_score.lift_score 是旧算法遗留列，模型已删除但表结构没迁移，
    NOT NULL 约束导致"首次新建快照"的股票 INSERT 必然失败（老股票 UPDATE 不受影响）。
    """
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).all()
        existing = {r[1] for r in rows}
        if column in existing:
            conn.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))
            conn.commit()
            logger.info("迁移：删除 %s.%s 残留列", table, column)


def init_db() -> None:
    """启动期编排：seed 复制 → 模型迁移 → create_all → 增量列迁移。"""
    from .migrations import (
        _migrate_ai_report_horizon,
        _migrate_ai_report_unique_created_at,
        _migrate_stock_score_composite_pk,
    )
    from .seed import _seed_from_bundle

    # 打包态首启动：从包内 seed.sqlite 复制出带全 A 元数据的初始库
    _seed_from_bundle()
    # 先做表级重建迁移（create_all 不会修改老表的约束）
    _migrate_ai_report_horizon()
    _migrate_ai_report_unique_created_at()

    from app.models import (  # noqa: F401
        ai_report,
        ai_report_review,
        capital_flow,
        kline,
        position,
        setting,
        stock,
        stock_dividend,
        stock_group,
        stock_score,
        stock_score_combined,
        sync_log,
    )

    SQLModel.metadata.create_all(engine)

    # 删除 stock_score 残留的 lift_score 列（模型已移除；NOT NULL 导致首次新建快照失败）
    _migrate_drop_column("stock_score", "lift_score")

    # stock_score.scan_scope：记录每次扫描范围，避免不同 scope 扫描混在同一天
    _migrate_add_column("stock_score", "scan_scope", "TEXT")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE stock_score SET scan_scope = 'all'
                WHERE scan_scope IS NULL AND scan_date IN (
                    SELECT scan_date FROM stock_score WHERE scan_scope IS NULL
                    GROUP BY scan_date HAVING COUNT(*) > 500
                )
                """
            )
        )
        conn.execute(text("UPDATE stock_score SET scan_scope = 'watchlist' WHERE scan_scope IS NULL"))

    # stock_score.scan_timeframe：打分周期（daily/weekly）；旧数据按 daily 回填
    _migrate_add_column("stock_score", "scan_timeframe", "TEXT NOT NULL DEFAULT 'daily'")
    with engine.begin() as conn:
        conn.execute(text("UPDATE stock_score SET scan_timeframe = 'daily' WHERE scan_timeframe IS NULL"))

    # 复合主键 (code, scan_timeframe)：daily/weekly 各留一份缓存，互不覆盖
    _migrate_stock_score_composite_pk()

    # ai_report.extras_json（老 DB 无此列）
    _migrate_add_column("ai_report", "extras_json", "TEXT")

    # stock_score_combined 详情可解释字段
    _migrate_add_column("stock_score_combined", "demote_reason", "TEXT")
    _migrate_add_column("stock_score_combined", "space_pct", "FLOAT")
    _migrate_add_column("stock_score_combined", "hist_golden_peak_pct", "FLOAT")
    _migrate_add_column("stock_score_combined", "hist_golden_peak_median", "FLOAT")
    _migrate_add_column("stock_score_combined", "weekly_signal_gain_pct", "FLOAT")
    _migrate_add_column("stock_score_combined", "daily_close", "FLOAT")
    _migrate_add_column("stock_score_combined", "daily_pct_chg", "FLOAT")
    _migrate_add_column("stock_score_combined", "weekly_untrusted_rebound", "BOOLEAN DEFAULT 0")
    _migrate_add_column("stock_score_combined", "daily_untrusted_rebound", "BOOLEAN DEFAULT 0")
    _migrate_add_column("stock_score_combined", "hist_death_trough_pct", "FLOAT")
    _migrate_add_column("stock_score_combined", "hist_death_trough_median", "FLOAT")
    _migrate_add_column("stock_score_combined", "weekly_is_golden", "BOOLEAN")

    # stock 扩展字段
    _migrate_add_column("stock", "pinned", "BOOLEAN DEFAULT 0")
    _migrate_add_column("stock", "group_id", "INTEGER")
    _migrate_add_column("stock", "note", "TEXT")
    _migrate_add_column("stock", "group_ids", "TEXT")

    # kline_daily.finalized：该 bar 是否收盘后写入的定稿数据（盘中快照 False）。
    # 存量行全部默认 1（历史 bar 天然定稿）。
    _migrate_add_column("kline_daily", "finalized", "BOOLEAN DEFAULT 1")
