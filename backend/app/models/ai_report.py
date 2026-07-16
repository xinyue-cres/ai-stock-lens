from datetime import date, datetime

from sqlmodel import Field, SQLModel, UniqueConstraint


class AIReport(SQLModel, table=True):
    __tablename__ = "ai_report"
    __table_args__ = (
        # created_at 天然唯一化。同一天同 horizon 允许多次生成，每次一条新记录。
        UniqueConstraint("code", "model", "horizon", "created_at", name="uq_report_key"),
    )

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(index=True)
    as_of_date: date = Field(index=True)
    model: str
    horizon: str = Field(default="medium", description="short | medium | combined")
    report_md: str
    verdict: str = Field(description="bullish | neutral | bearish | caution")
    confidence: float | None = None
    summary: str | None = None
    extras_json: str | None = Field(default=None, description="key_signals/risks/scenarios 的 JSON 序列化")
    created_at: datetime = Field(default_factory=datetime.now)
