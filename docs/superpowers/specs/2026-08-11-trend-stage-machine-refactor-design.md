# 选股趋势状态机重构设计

日期：2026-08-11
状态：已获用户批准（brainstorming 流程）
关联模块：`backend/app/features/trend_judge.py`、`backend/app/features/stock_scorer.py`、`backend/app/models/stock_score.py`、`frontend/src/pages/Scoreboard/**`

## 背景与动机

当前选股页的趋势状态机（`_decide_stage`）有 6 个枚举，但实际产出只有 4 个，存在明显的状态空间盲区：

1. **死叉态被"一刀切"**：死叉态只有两个出口——`range`（历史可靠）或 `downtrend`（历史差）。完全忽略了「下跌过峰」（MACD 绿柱回升、下跌动能衰竭的见底信号）和 DIF 斜率（修复/走弱）这两个最有效的见底维度。用户明确提出：死叉 + 下跌过峰应该标记为「左侧机会」，比金叉确认后（右侧）更早、更高风险、更高收益。
2. **金叉态缺"力度"维度**：金叉态只看"位置"（过热/回踩/贴轨），不看"这次金叉的质量"（柱体放大=真启动 vs 柱体缩小=弱金叉）。
3. **`strong_uptrend` 是僵尸状态**：该枚举存在于 `STAGE_PALETTE`、模型字段、AI prompt，但 `_decide_stage` 从未产出过它。没有一个状态表达「金叉确认后、健康上涨、可以持有但别追高」，这类票目前被错误归入 `pullback_entry`（语义是"可入手/新买"）。
4. **`range` 是垃圾桶**：金叉柱缩小 / 死叉可靠 / 贴下轨 / 胜率不足，四类截然不同的处境全塞进 `range`。

## 设计目标

1. 补全死叉态：新增 `left_entry` 左侧机会状态
2. 补全金叉态力度维度：新增 `weak_golden` 弱势金叉状态
3. 复活僵尸 `strong_uptrend`，让"持有别追高"有明确出口
4. 细化 `pullback_entry`、`overheat`、`downtrend` 的判定条件，`range` 不再是垃圾桶
5. 明确 `can_entry` 的两档语义：安全可入手 vs 高风险可入手

## 目标状态机（8 状态）

| 枚举 | 标签 | can_entry | 语义 |
|---|---|---|---|
| `pullback_entry` | 可入手 | ✅ 安全 | 金叉态·回踩/刚启动·历史可靠 |
| `left_entry` | 左侧机会 | ✅ 高风险 | 死叉态·下跌过峰·历史可靠·轻仓 |
| `strong_uptrend` | 上升趋势 | ❌ 持有 | 金叉态·强势·已涨·别追高 |
| `weak_golden` | 弱势金叉 | ❌ | 金叉态·柱体缩小·等回踩 |
| `overheat` | 过热 | ❌ | 贴上轨·非强趋势 |
| `downtrend` | 下跌趋势 | ❌ | 死叉·无见底·或高位刚死叉 |
| `range` | 震荡 | ❌ | 观望（贴下轨/胜率不足/信号不明） |
| `insufficient` | 数据不足 | ❌ | 数据 <60 根 |

## 判定流程（决策树）

```
输入：golden / pct_b / dist_high / signal_score / peak_winrate / bar_shrinking / adx / dif_slope

if 金叉态:
    # 1. 过热度（非强趋势才叫过热；强趋势贴轨是顺势）
    if %B > 0.85 and ADX < 25:              → overheat
    # 2. 强趋势中已涨一段 → 持有别追高（复活僵尸）
    if ADX >= 25 且 距金叉涨幅 > 8% 且 柱体未缩小: → strong_uptrend
    # 3. 动能掉头 → 别追
    if bar_shrinking:                       → weak_golden
    # 4. 深跌首个金叉但历史不可靠
    if dist_high < -0.4 and signal_score < 72: → downtrend
    # 5. 历史可靠 + 回踩/刚启动 + 未过热 → 真正可入手
    if signal_score >= 72 且 peak_winrate >= 50 且 %B <= 0.85: → pullback_entry
    # 6. 剩余：贴下轨 / 胜率不足 / 空间不足 → 观望
    → range

else 死叉态:
    # 1. 左侧机会：动能衰竭见底 + 历史可靠 → 高风险轻仓
    #    下跌过峰判定：bar_shrinking == False（MACD 绿柱单日回升 = 下跌动能衰竭）
    if bar_shrinking is False 且 signal_score >= 72: → left_entry
    # 2. 高位刚死叉 / 历史差 → 回避
    if dist_high > -0.1 或 signal_score < 72:    → downtrend
    # 3. 其余 → 观望
    → range

数据不足 → insufficient
```

### 判定条件说明

- **`bar_shrinking` 双义**：`bar_shrinking=True` 表示 MACD 柱单日缩小（`当日 < (昨日+前日)/2`）。
  - 金叉态下 `True` = 上涨动能掉头（上涨过峰）→ `weak_golden`
  - 死叉态下 `False` = 绿柱回升、下跌动能衰竭（下跌过峰）→ `left_entry` 候选
- **`ADX` 阈值 25**：经验值，强趋势判定线（后续可用数据校准）
- **`距金叉涨幅 > 8%`**：经验值，判定"已涨一段"（后续可校准）
- **`dist_high > -0.1`**：距 60 日高点回撤 <10%，视为"高位刚死叉"，比深跌死叉风险更高
- **`peak_winrate >= 50`**：历史金叉冲过 +5% 的占比，可靠性门槛

## can_entry 两档语义

`can_entry` 保持布尔字段（`pullback_entry` 和 `left_entry` 都算可入手 `True`），**不改 DB 字段**。两档区分通过前端判断 `trend_stage` 实现：

- **`pullback_entry`（安全可入手）**：`can_entry=True` + `trend_stage=pullback_entry`，正常可买，绿色系
- **`left_entry`（左侧机会·高风险）**：`can_entry=True` + `trend_stage=left_entry`，可入但**轻仓**，紫色/橙色系 + 标签「左侧·轻仓」，明确提示高风险高收益

前端在 `ScoreRow` / `ScoreDetail` 通过 `trend_stage` 区分两档的色系与提示，后端字段不变（避免迁移成本）。

## 涉及改动

### 后端

1. **`trend_judge.py`**：
   - `_decide_stage` 签名扩展：传入 `adx`、`dif_slope`（或从 cache 读取）
   - 新增枚举产出：`left_entry`、`weak_golden`、`strong_uptrend`
   - `_REASONS` 增加新状态的文案
   - `_entry_reason` 细化各状态的触发原因链
   - 补单测：每个新状态至少一条路径 + 边界（弱金叉 vs 可入手、左侧 vs 下跌、强趋势 vs 可入手）
2. **`stock_score.py`**：`trend_stage` 字段的 description 更新枚举列表
3. **`stock_scorer.py`**（如需）：`compute_indicator_cache` 已含 adx/dif_slope，确认 `judge_trend` 拿到

### 前端

4. **`api/score.ts`**：`TrendStage` 类型加 `left_entry`、`weak_golden`
5. **`constants.ts`**：`STAGE_PALETTE` 加新状态样式：
   - `left_entry`：紫色系（高风险）
   - `weak_golden`：橙色系（别追）
   - `strong_uptrend`：已有，保持红色系但明确"持有别追高"语义
6. **`ScoreRow.tsx` / `ScoreDetail.tsx`**：can_entry 两档区分展示（左侧机会·轻仓提示）

## 验证

1. 单测：`python -m pytest tests/test_trend_judge.py`（覆盖 8 状态全路径）
2. 前端：`tsc --noEmit`
3. 实盘验证：重扫后抽查——
   - 死叉 + 下跌过峰 + 历史可靠 → 显示「左侧机会」
   - 金叉 + 柱体缩小 → 显示「弱势金叉」
   - 强趋势金叉已涨 → 显示「上升趋势」
   - 金叉回踩历史可靠 → 仍「可入手」

## 风险与备注

- **左侧机会的风险提示**：`left_entry` 是左侧抄底，逆势，必须在前端显著提示"轻仓/高风险"，避免误当安全可入手
- **阈值经验值**：ADX 25 / 涨幅 8% / 高位 10% 均为经验值，上线后可用历史数据校准
- **重扫要求**：改状态机后需重扫才能让排行反映新标签（用户自定时机，不自动触发）
