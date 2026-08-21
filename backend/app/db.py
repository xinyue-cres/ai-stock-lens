import logging
from collections.abc import Generator

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
    # 先做迁移，因为 create_all 不会修改老表的约束
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

    # 迁移：删除 stock_score 残留的 lift_score 列（模型已移除；NOT NULL 导致首次新建快照失败）
    _migrate_drop_column("stock_score", "lift_score")

    # 迁移：stock_score.scan_scope——记录每次扫描范围，避免不同 scope 扫描混在同一天
    # 导致列表按全局最新 scan_date 显示时串范围（切全 A 却显示上次分组扫描的批次）
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
        conn.execute(
            text("UPDATE stock_score SET scan_scope = 'watchlist' WHERE scan_scope IS NULL")
        )

    # 增量迁移：stock_score.scan_timeframe——打分基于的周期（daily/weekly）；旧数据按 daily 回填
    _migrate_add_column("stock_score", "scan_timeframe", "TEXT NOT NULL DEFAULT 'daily'")
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE stock_score SET scan_timeframe = 'daily' WHERE scan_timeframe IS NULL")
        )

    # 增量迁移：stock_score 复合主键 (code, scan_timeframe)——daily/weekly 各留一份缓存，互不覆盖
    _migrate_stock_score_composite_pk()

    # 增量迁移：ai_report.extras_json（老 DB 无此列）
    _migrate_add_column("ai_report", "extras_json", "TEXT")

    # 增量迁移：stock.pinned
    _migrate_add_column("stock", "pinned", "BOOLEAN DEFAULT 0")

    # 增量迁移：stock.group_id + stock.note + stock.group_ids
    _migrate_add_column("stock", "group_id", "INTEGER")
    _migrate_add_column("stock", "note", "TEXT")
    _migrate_add_column("stock", "group_ids", "TEXT")


def _migrate_ai_report_horizon() -> None:
    """把 ai_report 表升级到含 horizon 的新 schema，并把 UNIQUE 扩展到 horizon。

    SQLite 的表级 UNIQUE 约束无法用 ALTER 修改，唯一办法是重建表。
    """
    with engine.begin() as conn:
        # 表存在？（新库直接跳过，交给 create_all）
        exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_report'")
        ).first()
        if not exists:
            return

        cols = {r[1] for r in conn.execute(text("PRAGMA table_info(ai_report)")).all()}
        if "horizon" in cols:
            return  # 已经迁移过

        # 检测 extras_json 是否已存在（可能上一次迁移已加），影响 SELECT 语句
        has_extras = "extras_json" in cols

        conn.execute(
            text(
                """
                CREATE TABLE ai_report_new (
                    id INTEGER PRIMARY KEY,
                    code TEXT NOT NULL,
                    as_of_date DATE NOT NULL,
                    model TEXT NOT NULL,
                    horizon TEXT NOT NULL DEFAULT 'medium',
                    report_md TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    confidence REAL,
                    summary TEXT,
                    extras_json TEXT,
                    created_at DATETIME NOT NULL,
                    CONSTRAINT uq_report_key UNIQUE (code, as_of_date, model, horizon)
                )
                """
            )
        )
        extras_col = "extras_json" if has_extras else "NULL"
        conn.execute(
            text(
                f"""
                INSERT INTO ai_report_new
                    (id, code, as_of_date, model, horizon, report_md, verdict,
                     confidence, summary, extras_json, created_at)
                SELECT id, code, as_of_date, model, 'medium', report_md, verdict,
                       confidence, summary, {extras_col}, created_at
                FROM ai_report
                """
            )
        )
        conn.execute(text("DROP TABLE ai_report"))
        conn.execute(text("ALTER TABLE ai_report_new RENAME TO ai_report"))
        conn.execute(text("CREATE INDEX ix_ai_report_code ON ai_report(code)"))
        conn.execute(text("CREATE INDEX ix_ai_report_as_of_date ON ai_report(as_of_date)"))


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session


def _migrate_ai_report_unique_created_at() -> None:
    """把 ai_report UNIQUE 从 (code,as_of_date,model,horizon) 改为 (code,model,horizon,created_at)。

    允许同日多次生成 AI 报告，每次一行新纪录。SQLite 表级 UNIQUE 无法 ALTER，仍需重建。
    """
    with engine.begin() as conn:
        row = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='ai_report'")
        ).first()
        if not row or not row[0]:
            return
        table_sql = row[0]
        # 已是新约束（含 created_at）→ 跳过
        if "UNIQUE (code, model, horizon, created_at)" in table_sql:
            return
        # 老约束会包含 as_of_date；不含则可能是全新表由 SQLAlchemy 创建的新版
        if "as_of_date" not in table_sql.split("UNIQUE")[-1]:
            return

        conn.execute(
            text(
                """
                CREATE TABLE ai_report_new (
                    id INTEGER PRIMARY KEY,
                    code TEXT NOT NULL,
                    as_of_date DATE NOT NULL,
                    model TEXT NOT NULL,
                    horizon TEXT NOT NULL DEFAULT 'medium',
                    report_md TEXT NOT NULL,
                    verdict TEXT NOT NULL,
                    confidence REAL,
                    summary TEXT,
                    extras_json TEXT,
                    created_at DATETIME NOT NULL,
                    CONSTRAINT uq_report_key UNIQUE (code, model, horizon, created_at)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO ai_report_new
                    (id, code, as_of_date, model, horizon, report_md, verdict,
                     confidence, summary, extras_json, created_at)
                SELECT id, code, as_of_date, model, horizon, report_md, verdict,
                       confidence, summary, extras_json, created_at
                FROM ai_report
                """
            )
        )
        conn.execute(text("DROP TABLE ai_report"))
        conn.execute(text("ALTER TABLE ai_report_new RENAME TO ai_report"))
        conn.execute(text("CREATE INDEX ix_ai_report_code ON ai_report(code)"))
        conn.execute(text("CREATE INDEX ix_ai_report_as_of_date ON ai_report(as_of_date)"))


def _migrate_stock_score_composite_pk() -> None:
    """把 stock_score 主键从 (code) 重建为 (code, scan_timeframe) 复合。

    背景：daily/weekly 各自扫描结果如果共用 (code) 单主键，weekly 扫描会覆盖同 code
    的 daily 行（数据真的丢）。改成 (code, scan_timeframe) 复合主键后两条腿互不覆盖，
    列表按当前查看周期过滤。

    SQLite 不支持 ALTER PK，需要 create_new + copy + drop + rename。
    检测方式：当前主键若只含 code 一列就重建；若已是复合则跳过（幂等）。
    """
    with engine.begin() as conn:
        cols = conn.execute(text("PRAGMA table_info(stock_score)")).all()
        if not cols:
            return  # 表不存在，等 SQLModel.metadata.create_all 用新模型创建
        pk_cols = [r[1] for r in cols if r[5] > 0]  # PRAGMA 第 5 列是 pk 顺序
        pk_cols.sort(key=lambda c: next(r[5] for r in cols if r[1] == c))
        if pk_cols == ["code", "scan_timeframe"]:
            return  # 已是复合 PK
        # 旧 (code) 单主键或其他形态 → 重建
        logger.info("迁移：重建 stock_score 为复合主键 (code, scan_timeframe)，旧 PK=%s", pk_cols)
        # 先把可能为 NULL 的 scan_timeframe 兜底到 daily，避免 INSERT ... SELECT 主键冲突
        conn.execute(text("UPDATE stock_score SET scan_timeframe='daily' WHERE scan_timeframe IS NULL"))
        # 如果同一 (code, scan_timeframe) 有多行（理论上不应该），保留最新 scan_date 的一行
        conn.execute(
            text(
                """
                DELETE FROM stock_score WHERE rowid NOT IN (
                    SELECT MAX(rowid) FROM stock_score GROUP BY code, scan_timeframe
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE stock_score_new (
                    code TEXT NOT NULL,
                    scan_timeframe TEXT NOT NULL,
                    name TEXT,
                    is_fund BOOLEAN,
                    scan_date DATE,
                    scan_scope TEXT,
                    as_of_date DATE,
                    total_score FLOAT,
                    signal_score FLOAT,
                    band_score FLOAT,
                    dividend_score FLOAT,
                    close FLOAT,
                    pct_chg FLOAT,
                    turnover FLOAT,
                    hist_vol FLOAT,
                    adx FLOAT,
                    dividend_yield FLOAT,
                    trend_stage TEXT,
                    can_entry BOOLEAN,
                    entry_reason TEXT,
                    components_json TEXT,
                    PRIMARY KEY (code, scan_timeframe)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO stock_score_new
                    (code, scan_timeframe, name, is_fund, scan_date, scan_scope, as_of_date,
                     total_score, signal_score, band_score, dividend_score,
                     close, pct_chg, turnover, hist_vol, adx, dividend_yield,
                     trend_stage, can_entry, entry_reason, components_json)
                SELECT code, scan_timeframe, name, is_fund, scan_date, scan_scope, as_of_date,
                       total_score, signal_score, band_score, dividend_score,
                       close, pct_chg, turnover, hist_vol, adx, dividend_yield,
                       trend_stage, can_entry, entry_reason, components_json
                FROM stock_score
                """
            )
        )
        conn.execute(text("DROP TABLE stock_score"))
        conn.execute(text("ALTER TABLE stock_score_new RENAME TO stock_score"))
        conn.execute(text("CREATE INDEX ix_stock_score_scan_date ON stock_score(scan_date)"))
        conn.execute(text("CREATE INDEX ix_stock_score_scan_scope ON stock_score(scan_scope)"))
        conn.execute(text("CREATE INDEX ix_stock_score_scan_timeframe ON stock_score(scan_timeframe)"))
