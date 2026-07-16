from datetime import datetime

from sqlmodel import Field, SQLModel


class SyncLog(SQLModel, table=True):
    __tablename__ = "sync_log"

    id: int | None = Field(default=None, primary_key=True)
    started_at: datetime = Field(default_factory=datetime.now, index=True)
    finished_at: datetime | None = None
    status: str = Field(description="success | failed | partial")
    stocks_synced: int = 0
    error_msg: str | None = None
