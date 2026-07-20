from datetime import datetime

from sqlmodel import Field, SQLModel


class StockGroup(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
