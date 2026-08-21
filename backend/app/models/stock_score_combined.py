"""日周合并评判结果表：每只标的一行，包含 weekly/daily 双方核心指标 + 综合结论。"""
from datetime import date

from sqlmodel import Field, SQLModel


class StockScoreCombined(SQLModel, table=True):
    __tablename__ = "stock_score_combined"

    code: str = Field(primary_key=True)
    name: str = Field(default="")
    is_fund: bool = Field(default=False)
    scan_date: date = Field(index=True, description="扫描日期")
    scan_scope: str | None = Field(default=None, index=True)

    # weekly（方向层）
    weekly_total: float | None = Field(default=None)
    weekly_signal: float | None = Field(default=None)
    weekly_stage: str | None = Field(default=None)
    weekly_peak_signal: str | None = Field(default=None)
    weekly_peak_conf: int | None = Field(default=None)

    # daily（时机层）
    daily_total: float | None = Field(default=None)
    daily_signal: float | None = Field(default=None)
    daily_stage: str | None = Field(default=None)
    daily_peak_signal: str | None = Field(default=None)
    daily_peak_conf: int | None = Field(default=None)

    # 综合
    combined_score: float = Field(default=0.0)
    combined_stage: str = Field(default="watch", index=True,
                                description="strong_buy/buy/watch_buy/deep_pullback_entry/light_buy/watch/avoid")
    can_entry: bool = Field(default=False, description="是否可入手（强买/买入/轻仓/深度回踩）")
    entry_reason: str | None = Field(default=None, description="操作建议主文")
    trade_hint: str | None = Field(default=None, description="仓位/止损等操作提示")

    as_of_date: date | None = Field(default=None)
