"""AI 报告复盘：记录报告发布后每个交易日的命中/正确性判断。"""
from datetime import date, datetime

from sqlmodel import Field, SQLModel, UniqueConstraint


class AIReportReview(SQLModel, table=True):
    __tablename__ = "ai_report_review"
    __table_args__ = (
        UniqueConstraint("report_id", "review_date", name="uq_review_key"),
    )

    id: int | None = Field(default=None, primary_key=True)
    report_id: int = Field(index=True, description="被复盘的 AIReport.id")
    code: str = Field(index=True, description="冗余字段方便按股票查询")
    as_of_date: date = Field(description="报告的 as_of_date，冗余便于对比")
    review_date: date = Field(index=True, description="复盘那一天（即数据交易日）")
    days_after: int = Field(description="review_date 距离 as_of_date 的交易日间隔")

    verdict_hit: str | None = Field(
        default=None,
        description="verdict 与实际走势对照：hit | miss | pending | n/a",
    )
    price_change_pct: float | None = Field(
        default=None, description="review_date 收盘价相对 as_of_date 的涨跌幅"
    )
    scenarios_json: str | None = Field(
        default=None,
        description="每个 scenario 的命中评估结果 JSON："
        "[{index, direction, triggered, condition_results:[{kind,op,value,actual,ok}]}]",
    )
    triggered_count: int = Field(default=0, description="命中触发的 scenario 数量")
    total_scenarios: int = Field(default=0, description="有结构化 conditions 的 scenario 总数")

    notes: str | None = Field(default=None, description="人机可读摘要")
    created_at: datetime = Field(default_factory=datetime.now)
