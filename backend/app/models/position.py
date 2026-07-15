"""持仓：一票一条最新状态。用户手动录入 code / 数量 / 成本价。

不做交易流水表：修改就覆盖，避免过度设计。将来接券商 API 拿真实成交数据时再拆。
"""
from datetime import date, datetime

from sqlmodel import Field, SQLModel, UniqueConstraint


class Position(SQLModel, table=True):
    __tablename__ = "position"
    __table_args__ = (UniqueConstraint("code", name="uq_position_code"),)

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(index=True, description="股票代码，不强制外键关联 stock")
    quantity: int = Field(description="持股数（股）；0 表示已清仓但保留记录")
    cost_price: float = Field(description="加权平均成本价")
    opened_at: date = Field(description="首次建仓日")
    note: str | None = Field(default=None, description="用户备注")
    updated_at: datetime = Field(default_factory=datetime.utcnow)
