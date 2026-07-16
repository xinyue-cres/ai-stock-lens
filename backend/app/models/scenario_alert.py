from datetime import date, datetime

from sqlmodel import Field, SQLModel, UniqueConstraint


class ScenarioAlert(SQLModel, table=True):
    __tablename__ = "scenario_alert"
    __table_args__ = (
        UniqueConstraint("code", "report_id", "scenario_index", "triggered_date", name="uq_scenario_alert"),
    )

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(index=True)
    report_id: int = Field(index=True)
    horizon: str
    scenario_index: int
    trigger: str
    direction: str
    triggered_date: date
    created_at: datetime = Field(default_factory=datetime.utcnow)
