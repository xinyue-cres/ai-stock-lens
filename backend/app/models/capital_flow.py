from datetime import date

from sqlmodel import Field, SQLModel


class CapitalFlowDaily(SQLModel, table=True):
    __tablename__ = "capital_flow_daily"

    code: str = Field(primary_key=True, index=True)
    trade_date: date = Field(primary_key=True, index=True)
    main_net: float | None = Field(default=None, description="主力净流入（元）")
    super_large: float | None = None
    large: float | None = None
    medium: float | None = None
    small: float | None = None
