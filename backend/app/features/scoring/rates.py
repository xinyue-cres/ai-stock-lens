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
