from collections.abc import Generator

from sqlalchemy import text
from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

_settings = get_settings()

engine = create_engine(
    _settings.db_url,
    echo=False,
    connect_args={"check_same_thread": False},
)


def _migrate_add_column(table: str, column: str, ddl: str) -> None:
    """幂等的 ALTER TABLE ADD COLUMN（SQLite 简单迁移）。"""
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).all()
        existing = {r[1] for r in rows}
        if column not in existing:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
            conn.commit()


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
        scenario_alert,
        setting,
        stock,
        sync_log,
    )

    SQLModel.metadata.create_all(engine)

    # 增量迁移：ai_report.extras_json（老 DB 无此列）
    _migrate_add_column("ai_report", "extras_json", "TEXT")

    # 增量迁移：stock.pinned
    _migrate_add_column("stock", "pinned", "BOOLEAN DEFAULT 0")


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
