"""打分引擎共享常量：权重、阈值、周期校准。

所有可调参数集中此地，调参只改一个文件。
"""
from __future__ import annotations

# 综合分权重（金叉延续性 + 波段适配 + 股息）
W_GOLDEN = 0.70
W_BAND = 0.20
W_DIVIDEND = 0.10

_MIN_ROWS = 60  # 少于 60 根 bar 不评分（= 60 交易日 ≈ 3 个月 / = 60 周 ≈ 14 个月）

_GOLDEN_HORIZONS = (5, 10, 20)  # 金叉后延续观察窗口（已废弃：被史上峰值法替代）

# 动能加速度过峰阈值（A 方法）：acc_z = DIF 二阶导相对该股历史波动的 z-score。
# 方向由 acc_z 符号给出：acc_z < −_PEAK_Z = 动能急刹（顶部过峰）；acc_z > +_PEAK_Z = 动能急转（底部过峰）。
# 实时版验证：|acc_z|>1.0 报警率 ~19%（bar 旧判定 ~49%），|acc_z|>1.5 ~12.5%。取 1.0（预警宁可多报）。
_PEAK_Z = 1.0

# 周期校准的过峰置信度"强"档阈值（强档才决策降级；弱/极弱只前端提示）
_PEAK_CONF_STRONG_DAILY = 51   # 日线：误报率 ~57%
_PEAK_CONF_STRONG_WEEKLY = 40  # 周线：acc_z 分布系统性偏低，用 daily=51 会永远无 left_entry/overheat 触发

_PEAK_CONF_STRONG_BY_TF: dict[str, int] = {
    "daily": _PEAK_CONF_STRONG_DAILY,
    "weekly": _PEAK_CONF_STRONG_WEEKLY,
}

# 兼容老代码（默认 daily 语义）
_PEAK_CONF_STRONG = _PEAK_CONF_STRONG_DAILY

# 过峰"提示"档阈值：综合建议文案里附注日线过峰信号的最低置信度。
# 低于强档 51（不拦金叉），仅作详情补充说明——文案提示门槛应低于决策门槛。
_PEAK_CONF_HINT = 40

# 量价效率因子（eff4）：金叉→死叉周期内"每换手一遍流通盘涨多少"的近 4 周期均值。
# 回测（可实现口径·次日买持有到期卖）：日线 top5 全期 +2.4pp、2024.9后 +0.9~2.7pp、
# 2026 +2.4~6.7pp；周线 top5 全期 +0.7~1.2pp、牛市段 +1.4~4.2pp——三段全正。
# 全史涨幅口径在周线腿可实现收益下系统性为负（-1.3~-3.5pp），eff4 是唯一两腿
# 都存活的量价修正，故双线混入 50%。
_EFF_K = 4           # 近 K 个已完结金叉周期
_EFF_MIN_TURNS = 0.3  # 周期累计换手率下限（防除零；不足的周期跳过）
# eff 归一上限：全样本分布 p90≈3.1、max≈3.8（默认 4 时中位票只拿 52 分→分布压平）。
# 锚点降到 3 让"前 10% 接近满分、中位 70 分、尾巴拉开"——与 demarket 锚点取 p90 同哲学。
_EFF_NORM_HI = 3.0
_EFF_BLEND = 0.5      # eff4 分与全史涨幅分的混合权重
