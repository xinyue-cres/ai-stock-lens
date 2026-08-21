"""评分 API 请求模型。"""
from pydantic import BaseModel


class ScanRequest(BaseModel):
    scope: str = "all"  # all | watchlist | group
    codes: list[str] | None = None
    force: bool = False
    group_id: int | None = None  # 兼容旧字段：单个分组
    group_ids: list[int] | None = None  # scope=watchlist 时按多个自选分组过滤（任意匹配）
    timeframe: str = "daily"  # daily | weekly：打分基于的 K 线周期（bar 重采样在 scoring_service 内做）


class SummarizeRequest(BaseModel):
    scope: str = "all"  # all | watchlist | group（仅用于给 AI 说明查看范围）
    group_ids: str | None = None
    limit: int = 15


class AnalyzeBatchRequest(BaseModel):
    scope: str = "all"
    group_ids: str | None = None
    limit: int = 10
