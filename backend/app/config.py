import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_db_path() -> str:
    """数据库默认位置。

    - 打包态（PyInstaller）：exe 旁 data/app.db（便携，绿色软件体验）
    - 源码态：backend/data/app.db
    """
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(sys.executable), "data", "app.db")
    return "data/app.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ai_provider: str = "deepseek"
    ai_api_key: str = ""
    ai_base_url: str = "https://api.deepseek.com/v1"
    ai_model: str = "deepseek-chat"

    datasource_primary: str = "akshare"
    tushare_token: str = ""

    sync_enabled: bool = False  # 默认关闭：同步/复盘定时任务全部不启动（环境变量 SYNC_ENABLED=true 可局部打开）
    sync_cron_hour: int = 16
    sync_cron_minute: int = 10

    # 选股打分扫描（仅手动触发；scan_enabled/scan_cron_* 已移除，不再定时自动扫全 A）
    # scan 网络拉取并发：12+ 会触发东财 rate limit 连续失败进入 300s cooldown，
    # 触发 fallback 到 baostock/sina（全局锁串行），扫描全程卡死。保持 6 保守保瑜
    scan_concurrency: int = 6
    scan_kline_bars: int = 1000  # 扫描拉取约 4 年（覆盖完整牛熊周期，避免 2 年窗口只含单边牛市）

    @property
    def scan_kline_days(self) -> int:
        """扫描拉取的自然日窗口：1000 交易日 ≈ 1.5 倍自然日 ≈ 4.1 年。

        1.4 只够 ~960 交易日（自然日含周末节假日，交易日占比 ~0.66），
        会导致 _load_cached_kline 的 ≥1000 根判定永远不足 → 缓存命中失效全走网络。
        """
        return int(self.scan_kline_bars * 1.5)

    app_log_level: str = "INFO"
    # 默认随运行环境：打包态 exe 旁 data/，源码态 backend/data/；可被 .env 覆盖
    db_path: str = Field(default_factory=_default_db_path)

    @field_validator("db_path", mode="before")
    @classmethod
    def _empty_db_path_fallback(cls, v: object) -> object:
        """.env 里 DB_PATH 留空时回退默认位置（避免空串覆盖成内存库）。"""
        if v is None or v == "":
            return _default_db_path()
        return v

    @property
    def db_url(self) -> str:
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{self.db_path}"


@lru_cache
def get_settings() -> Settings:
    return Settings()
