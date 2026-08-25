from datetime import date

from sqlmodel import Field, SQLModel


class KlineDaily(SQLModel, table=True):
    __tablename__ = "kline_daily"

    code: str = Field(primary_key=True, index=True)
    trade_date: date = Field(primary_key=True, index=True)
    open: float
    high: float
    low: float
    close: float
    volume: int = Field(description="成交量，单位：股（全链路统一为股，东财*100换算）")
    amount: float = Field(description="成交额，单位：元")
    turnover: float | None = Field(default=None, description="换手率 %")
    pct_chg: float | None = Field(default=None, description="涨跌幅 %")
    # 该 bar 是否为收盘后写入的定稿数据。盘中拉取的今日 bar 是实时快照
    # （价格随时间变），必须收盘后重拉才可信——此标记供同步跳过判断用：
    # finalized=True 的今日 bar 才允许跳过远程拉取（半成品会一直重拉到收盘）。
    # 历史行（非今日）天然视为定稿，读取时默认 True。
    finalized: bool | None = Field(default=True, description="是否收盘后写入的定稿 bar（盘中快照为 False）")
