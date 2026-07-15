from datetime import date

from sqlmodel import Field, SQLModel


class KlineDaily(SQLModel, table=True):
    __tablename__ = "kline_daily"

    code: str = Field(primary_key=True, index=True)
    trade_date: date = Field(primary_key=True, index=True)
    open: float
    high: float
    low: float
    close: float
    volume: int = Field(description="成交量，单位：手")
    amount: float = Field(description="成交额，单位：元")
    turnover: float | None = Field(default=None, description="换手率 %")
    pct_chg: float | None = Field(default=None, description="涨跌幅 %")
