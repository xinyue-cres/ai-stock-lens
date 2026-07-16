"""Provider 基类：熔断三件套 + capabilities + 通用工具函数。

每个具体 Provider 只做"和一个数据源对话"这件事，不做 fallback；fallback 由
DataRouter 负责编排。
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Capabilities:
    """Provider 能力声明；Router 按此决定挂不挂在某条链上。"""

    stock_daily: bool = False
    index_daily: bool = False
    has_turnover: bool = False  # 日线里是否原生带换手率
    stock_list: bool = False    # 是否能拉全 A 股列表


def infer_market(code: str) -> str:
    """按代码前缀推交易所：SH / SZ / BJ。默认 SH。"""
    if code.startswith(("60", "68", "9", "51", "56", "58")):
        return "SH"
    if code.startswith(("00", "30", "20", "15", "16")):
        return "SZ"
    if code.startswith(("43", "83", "87", "88")):
        return "BJ"
    return "SH"


def sina_symbol(code: str) -> str:
    """转成新浪接口需要的 sh600519 / sz000001 格式。"""
    return f"{infer_market(code).lower()}{code}"


def is_fund_code(code: str) -> bool:
    """判断是否为场内基金（ETF/LOF）代码。"""
    return code.startswith(("51", "56", "58", "15", "16"))


class BaseProvider:
    """所有 Provider 的基类，实现熔断状态机。

    子类只需重写具体的 fetch 方法；调用失败时抛异常，Router 会捕获并调 record_failure。
    """

    name: str = "base"
    capabilities: Capabilities = Capabilities()

    # 熔断默认参数：连续 3 次失败进入 300 秒冷却
    _failure_threshold: int = 3
    _cooldown_seconds: int = 300

    def __init__(self) -> None:
        self._failures: int = 0
        self._cooldown_until: float = 0.0

    def is_healthy(self) -> bool:
        """是否可用：不处于冷却期。"""
        return time.time() >= self._cooldown_until

    def record_success(self) -> None:
        self._failures = 0
        self._cooldown_until = 0.0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self._failure_threshold:
            self._cooldown_until = time.time() + self._cooldown_seconds
            logger.warning(
                "[%s] 连续失败 %d 次，进入 %d 秒冷却",
                self.name, self._failures, self._cooldown_seconds,
            )
