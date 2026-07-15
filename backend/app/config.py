from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ai_provider: str = "deepseek"
    ai_api_key: str = ""
    ai_base_url: str = "https://api.deepseek.com/v1"
    ai_model: str = "deepseek-chat"

    datasource_primary: str = "akshare"
    tushare_token: str = ""

    sync_enabled: bool = True
    sync_cron_hour: int = 16
    sync_cron_minute: int = 10

    app_log_level: str = "INFO"
    db_path: str = "/app/data/app.db"

    @property
    def db_url(self) -> str:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.db_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
