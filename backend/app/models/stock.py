from datetime import datetime

from sqlmodel import Field, SQLModel


class Stock(SQLModel, table=True):
    code: str = Field(primary_key=True, description="6 位代码，如 600519")
    name: str = Field(index=True)
    market: str = Field(description="SH / SZ / BJ")
    is_watchlist: bool = Field(default=False, index=True)
    pinned: bool = Field(default=False, index=True, description="置顶标记")
    added_at: datetime = Field(default_factory=datetime.now)
