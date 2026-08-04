"""选股打分结果表：每只标的一行，扫描时按 code 覆盖写最新结果。"""
from datetime import date

from sqlmodel import Field, SQLModel


class StockScore(SQLModel, table=True):
    __tablename__ = "stock_score"

    code: str = Field(primary_key=True)
    name: str = Field(default="")
    is_fund: bool = Field(default=False, description="ETF/LOF 标记（股息走中性）")
    scan_date: date = Field(index=True, description="扫描日期")
    as_of_date: date | None = Field(default=None, description="K 线最后交易日")

    total_score: float = Field(default=0.0, description="综合分 0-100")
    signal_score: float = Field(default=0.0, description="金叉死叉置信度")
    lift_score: float = Field(default=0.0, description="趋势质量")
    band_score: float = Field(default=0.0, description="波段适配")
    dividend_score: float = Field(default=0.0, description="股息")

    close: float | None = Field(default=None)
    pct_chg: float | None = Field(default=None)
    turnover: float | None = Field(default=None)
    hist_vol: float | None = Field(default=None)
    adx: float | None = Field(default=None)
    dividend_yield: float | None = Field(default=None)

    # 趋势判断（需求 2）
    trend_stage: str | None = Field(default=None, description="strong_uptrend/pullback_entry/overheat/downtrend/range")
    can_entry: bool | None = Field(default=None)
    entry_reason: str | None = Field(default=None)

    # 各维度原始指标明细（JSON）
    components_json: str | None = Field(default=None)
