"""日周合并评判结果表：每只标的一行，包含 weekly/daily 双方核心指标 + 综合结论。"""
from datetime import date

from sqlmodel import Field, SQLModel


class StockScoreCombined(SQLModel, table=True):
    __tablename__ = "stock_score_combined"

    code: str = Field(primary_key=True)
    name: str = Field(default="")
    is_fund: bool = Field(default=False)
    scan_date: date = Field(index=True, description="扫描日期")
    scan_scope: str | None = Field(default=None, index=True)

    # weekly（方向层）
    weekly_total: float | None = Field(default=None)
    weekly_signal: float | None = Field(default=None)
    weekly_stage: str | None = Field(default=None)
    weekly_peak_signal: str | None = Field(default=None)
    weekly_peak_conf: int | None = Field(default=None)
    # 反弹未确认：深跌中刚金叉但历史延续差 → 判 downtrend 回避，但市场状态是
    # 底部反弹初期非下跌——前端加"⚠反弹不可信"角标与真下跌区分（603833 实录）
    weekly_untrusted_rebound: bool | None = Field(default=False)

    # daily（时机层）
    daily_total: float | None = Field(default=None)
    daily_signal: float | None = Field(default=None)
    daily_stage: str | None = Field(default=None)
    daily_peak_signal: str | None = Field(default=None)
    daily_peak_conf: int | None = Field(default=None)
    daily_untrusted_rebound: bool | None = Field(default=False)

    # 综合
    combined_score: float = Field(default=0.0)
    combined_stage: str = Field(default="watch", index=True,
                                description="strong_buy/buy/watch_buy/deep_pullback_entry/light_buy/watch/avoid")
    can_entry: bool = Field(default=False, description="是否可入手（强买/买入/轻仓/深度回踩）")
    entry_reason: str | None = Field(default=None, description="操作建议主文")
    trade_hint: str | None = Field(default=None, description="仓位/止损等操作提示")
    demote_reason: str | None = Field(default=None, description="被降级原因（如 pct_b 贴上轨）")

    # 空间指标（供详情页显示参考，不入评分）
    space_pct: float | None = Field(default=None, description="距 BOLL 上轨的空间 %，越大上方空间越足；按 daily 算")
    # 历史金叉周期涨幅（该股的"气质"，比 60 日高更能代表预期空间；来自 signal_summary）
    hist_golden_peak_pct: float | None = Field(default=None, description="该股历史金叉周期峰值涨幅均值 %")
    hist_golden_peak_median: float | None = Field(default=None, description="该股历史金叉周期峰值涨幅中位 %")
    # 当前金叉已涨幅（这周 K 上的当前信号累计涨跌；供"剩余涨幅"推导）
    weekly_signal_gain_pct: float | None = Field(default=None, description="weekly 当前金叉状态下累计已涨幅 %")
    # 当日行情（来自 daily 腿；排行页同步后即时刷新的口径一致）
    daily_close: float | None = Field(default=None, description="最新收盘价（daily 腿）")
    daily_pct_chg: float | None = Field(default=None, description="当日涨跌幅 %（daily 腿）")

    as_of_date: date | None = Field(default=None)
