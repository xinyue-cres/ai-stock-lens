"""股息缓存表：近 3 年平均股息率，按 code 一行，定期刷新。"""
from datetime import date

from sqlmodel import Field, SQLModel


class StockDividend(SQLModel, table=True):
    __tablename__ = "stock_dividend"

    code: str = Field(primary_key=True)
    name: str | None = Field(default=None)
    avg_yield_3y: float | None = Field(default=None, description="近 3 年平均股息率（百分数，如 3.2 = 3.2%）")
    years: int = Field(default=0, description="参与平均的年度数")
    updated_at: date = Field(default_factory=date.today)
