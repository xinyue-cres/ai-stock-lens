"""选股打分结果表：每只标的在每个周期（daily/weekly）下各占一行。

主键是 (code, scan_timeframe) 复合——daily/weekly 互不覆盖，两条腿各自缓存。
"""
from datetime import date

from sqlmodel import Field, SQLModel


class StockScore(SQLModel, table=True):
    __tablename__ = "stock_score"

    code: str = Field(primary_key=True)
    scan_timeframe: str = Field(primary_key=True, description="打分基于的 K 线周期 daily/weekly；与 code 构成复合主键")
    name: str = Field(default="")
    is_fund: bool = Field(default=False, description="ETF/LOF 标记（股息走中性）")
    scan_date: date = Field(index=True, description="扫描日期")
    scan_scope: str | None = Field(default=None, index=True, description="扫描范围 all/watchlist/group")
    as_of_date: date | None = Field(default=None, description="K 线最后交易日")

    total_score: float = Field(default=0.0, description="综合分 0-100")
    signal_score: float = Field(default=0.0, description="金叉延续性")
    band_score: float = Field(default=0.0, description="波段适配")
    dividend_score: float = Field(default=0.0, description="股息")

    close: float | None = Field(default=None)
    pct_chg: float | None = Field(default=None)
    turnover: float | None = Field(default=None)
    hist_vol: float | None = Field(default=None)
    adx: float | None = Field(default=None)
    dividend_yield: float | None = Field(default=None)

    # 趋势判断（需求 2）
    trend_stage: str | None = Field(default=None, description="strong_uptrend/pullback_entry/overheat/weak_golden/left_entry/downtrend/range/insufficient")
    can_entry: bool | None = Field(default=None)
    entry_reason: str | None = Field(default=None)

    # 各维度原始指标明细（JSON）
    components_json: str | None = Field(default=None)
