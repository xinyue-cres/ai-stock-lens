from datetime import datetime

from sqlmodel import Field, SQLModel


class AppSetting(SQLModel, table=True):
    __tablename__ = "app_setting"

    key: str = Field(primary_key=True, description="设置键")
    value: str = Field(description="设置值（可为 JSON 字符串）")
    updated_at: datetime = Field(default_factory=datetime.utcnow)
