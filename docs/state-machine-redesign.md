# 状态机对称化改造方案

> 版本：v0.3（方案稿，未实施）
> 日期：2026-08-24
> 背景：当前系统买侧细化到 5 档，卖侧只有一个吸收一切的 `avoid`，与买侧严重不对称。本方案把综合状态机重构为绕“混沌持有态”对称的完整结构，并整理三层状态机（单腿趋势 / 过峰信号 / 综合档位）的全部状态与对应文本。

---

## 1. 现状：三层状态机及其缺陷

### 1.1 三层结构回顾

| 层 | 产出 | 档位数 | 语义 |
|---|---|---|---|
| ① 单腿趋势（trend_stage） | judge_trend 决策树 | 8 | 金叉驱动，买侧归因细（pullback/left/strong），卖侧归因粗（downtrend/overheat 吸收一切） |
| ② 综合档位（combined_stage） | combined_judge 矩阵 | 6+1 | (weekly, daily) 查 8×8 矩阵 → 6 档操作 + 1 档回避 |
| ③ 信号（current_state / peak_signal） | golden / peak 特征 | 6 + 6 | 纯展示，不进决策树 |

### 1.2 综合档位现状（7 档）

```
买侧（5 档）：
  strong_buy            重仓买入（双周共振金叉回踩）
  buy                   可买入
  watch_buy             观望买（周看好 + 日整理，等升级）
  deep_pullback_entry   深度回踩（周趋势内日超跌）
  light_buy             轻仓试（周中性 + 日起涨）
中央：
  watch                 观望（不动）
卖侧（仅 1 档）：
  avoid                 回避（吸收 6 种不同语义）
```

### 1.3 缺陷清单

1. **卖侧零颗粒度**：周线 downtrend、周线 overheat、双周 weak_golden 都落到同一个 `avoid`——“下跌趋势别接飞刀”和“涨过头该止盈”是相反的操作语义，却共用一档。
2. **`avoid` 建议自相矛盾**：`trade_hint`（“已持仓的尽快减仓”）要求先卖，但系统没有 sell 档位去指明卖多少、怎么卖。
3. **`watch` 语义双义**：它同时表示“没仓先别急”与“持仓先别动”，对两类用户其实是两种建议。
4. **极位态缺失**：有 `strong_buy`（双周共振），没有 `strong_sell`（双周共振走弱被 avoid 吞掉，无差异化）。
5. **买入后无镜像离场参考**：进入 strong_buy 后，什么信号该走，没有反向档位可挂钩。

---

## 2. 设计原则：对称轴与双不动点

### 2.1 对称轴 = 仓位视角中点

不是动量镜像（涨↔跌）、不是语义镜像（金叉↔死叉），而是**仓位操作视角**：

```
仓位操作方向：   减 0% ←——————● 50% ●——————→ 增 100%
                              对称轴
```

| 区域 | 档位 | 用户操作 |
|---|---|---|
| 满仓区 | strong_buy | 加仓到重仓 |
| 加仓区 | buy / watch_buy / light_buy | 逐步建仓 |
| 中央 | hold（持有） | 不动，等方向 |
| 减仓区 | light_sell / watch_sell / sell | 逐步减仓 |
| 清仓区 | strong_sell | 清仓退出 |
| 系统外 | avoid | 这票不该出现在仓位维度里 |

### 2.2 双不动点

对称系统有两个“自己映自己”的状态：

- **`hold`（持有，中央态）**：可买可卖的混沌态，答案只有“等”。它取代原 `watch`。
- **`avoid`（场外，系统外）**：系统**不评估**该票——数据不足、双周都假弱无信号等兜底态。不落在对称轴上，是对整个对称系统的短路开关。与卖侧极档 `strong_sell`（明确看空）区分：**avoid 是"没信息"，strong_sell 是"明确坏"**。

### 2.3 hold 与原 watch 的关系

- 原 watch 的“观望但票可交易”（多数）→ 入 **hold**
- 原 watch 的“假信号 / 弱信号不可交易”（weekly=weak_golden 等）→ 入 **avoid**

**为什么是 5 对镜像 + hold + avoid = 12 档，而非 6 对镜像？** 双数对称（纯镜像无中央）会强制把中性整理票硬塞进某个持仓档位；中央态才是最高频、最需要明确语义的位置。

---

## 3. 新综合档位表（12 档）

| # | combined_stage | 中文 | 仓位动作 | 矩阵来源（weekly × daily） |
|---|---|---|---|---|
| 1 | `strong_buy` | 强买信号 | 重仓买入 | 双周共振金叉回踩 |
| 2 | `buy` | 买入 | 中等仓位 | 周看好 + 日反弹 |
| 3 | `deep_pullback_entry` | 深度回踩 | 轻仓分批 | 周趋势内 + 日超跌 |
| 4 | `watch_buy` | 观察买 | 先盯 | 周看多 + 日整理 |
| 5 | `light_buy` | 轻仓试 | 轻仓 | 周中性 + 日起涨 |
| 6 | `hold` | 持有 | 不动 | 可交易态 + 无明确信号 |
| 7 | `light_sell` | 轻仓减 | 减仓 | 周走弱 + 日还活着 |
| 8 | `watch_sell` | 观察卖 | 先盯 | 周中性 + 日起弱 |
| 9 | `deep_rally_exit` | 反弹离场 | 分批减仓 | 周弱 + 日强反弹（离场窗口） |
| 10 | `sell` | 卖出 | 中大仓减 | 周走弱 + 日已弱 |
| 11 | `strong_sell` | 强卖信号 | 清仓 | 双周共振走弱 |
| 12 | `avoid` | 场外回避 | 不介入 | 系统不评估：数据不足 / 双周假弱无信号 |

结构：5 对镜像（strong / buy / watch / deep / light）+ hold（不动点）+ avoid（系统外）= 12 档。

### 镜像对设计要点

| 对 | 买侧 | 卖侧 | 镜像逻辑 |
|---|---|---|---|
| 极 | strong_buy | strong_sell | 双周同向共振：都金叉回踩 → 重仓；都死叉/过热 → 清 |
| 主 | buy | sell | 周线定基调 + 日线确认 |
| 观察 | watch_buy | watch_sell | 周方向已定 + 日整理：买侧等日线金叉升级，卖侧等日线死叉确认 |
| 深度 | deep_pullback_entry | deep_rally_exit | 周趋势 × 日极端：回调是加仓机会（深跌=假摔），反弹是减仓窗口（假反弹） |
| 轻 | light_buy | light_sell | 周中性 + 日首波信号：日先有动作，仓位先跟着看 |

---

## 4. 新决策矩阵（8×8）

> 规则：
> - 输入 `(weekly_stage, daily_stage)`，None 经 `or "insufficient"` 兜底；
> - daily wildcard：`(weekly, "*")` 表示该 weekly 下所有未列出 daily 组合的兜底；
> - 未列出的组合默认 `hold`。

```python
_MATRIX: dict[tuple[str, str], str] = {
    # ── weekly = pullback_entry（周趋势向上，可入手）─────────────────────────
    ("pullback_entry", "pullback_entry"):  "strong_buy",
    ("pullback_entry", "strong_uptrend"):  "buy",
    ("pullback_entry", "left_entry"):      "buy",
    ("pullback_entry", "range"):           "watch_buy",
    ("pullback_entry", "weak_golden"):     "watch_buy",
    ("pullback_entry", "downtrend"):       "deep_pullback_entry",  # 周趋势内日超跌 → 假摔，接
    ("pullback_entry", "overheat"):        "watch_sell",           # 周买但日已过热 → 拉不动
    ("pullback_entry", "insufficient"):    "hold",

    # ── weekly = strong_uptrend（周强上升趋势）─────────────────────────────
    ("strong_uptrend", "pullback_entry"):  "strong_buy",
    ("strong_uptrend", "strong_uptrend"):  "strong_buy",
    ("strong_uptrend", "left_entry"):      "light_buy",
    ("strong_uptrend", "range"):           "light_buy",
    ("strong_uptrend", "weak_golden"):     "hold",
    ("strong_uptrend", "downtrend"):       "deep_rally_exit",      # 周强 + 日走差 → 反弹逢高减
    ("strong_uptrend", "overheat"):        "sell",
    ("strong_uptrend", "insufficient"):    "hold",

    # ── weekly = range（周中性整理，可交易但无方向）────────────────────────
    ("range", "pullback_entry"):           "light_buy",
    ("range", "strong_uptrend"):           "light_buy",
    ("range", "left_entry"):               "light_buy",
    ("range", "range"):                    "hold",
    ("range", "weak_golden"):              "hold",
    ("range", "downtrend"):                "watch_sell",           # 周平 + 日入下跌 → 盯减
    ("range", "overheat"):                 "light_sell",
    ("range", "insufficient"):             "hold",

    # ── weekly = left_entry（周左侧机会，本身激进）─────────────────────────
    ("left_entry", "pullback_entry"):      "light_buy",
    ("left_entry", "strong_uptrend"):      "light_buy",
    ("left_entry", "left_entry"):          "hold",                 # 双侧都左侧 → 不动等金叉
    ("left_entry", "range"):               "hold",
    ("left_entry", "weak_golden"):         "watch_sell",           # 周左侧 + 日走弱 → 不恋战
    ("left_entry", "downtrend"):           "watch_sell",
    ("left_entry", "overheat"):            "deep_rally_exit",      # 周左 + 日过热 → 反弹就跑
    ("left_entry", "insufficient"):        "hold",

    # ── weekly = weak_golden（周假金叉不可靠，不推荐买入）──────────────────
    # 对持仓者借反弹减仓；双周都假弱 → 无法评估 → avoid
    ("weak_golden", "pullback_entry"):     "watch_sell",
    ("weak_golden", "strong_uptrend"):     "watch_sell",
    ("weak_golden", "left_entry"):         "deep_rally_exit",
    ("weak_golden", "range"):              "avoid",                # 周假弱 + 日无方向 → 不评估
    ("weak_golden", "weak_golden"):        "avoid",                # 双周假弱 → 不评估
    ("weak_golden", "downtrend"):          "avoid",                # 周假弱 + 日弱 → 不评估
    ("weak_golden", "overheat"):           "strong_sell",          # 假金叉 + 日过热 → 清
    ("weak_golden", "insufficient"):       "hold",

    # ── weekly = downtrend（周下跌，持仓者该走 / 未持仓者禁区）─────────────
    ("downtrend", "downtrend"):            "strong_sell",          # 双周共振死叉 → 清仓
    ("downtrend", "overheat"):             "sell",
    ("downtrend", "weak_golden"):          "sell",
    ("downtrend", "range"):                "sell",
    ("downtrend", "strong_uptrend"):       "deep_rally_exit",      # 日强反弹 = 出逃窗口
    ("downtrend", "pullback_entry"):       "watch_sell",
    ("downtrend", "left_entry"):           "watch_sell",
    ("downtrend", "insufficient"):         "avoid",                # 周弱 + 数据不足 → 不评估

    # ── weekly = overheat（周已涨过头，持仓者该走 / 未持仓者禁区）──────────
    ("overheat", "overheat"):              "strong_sell",          # 双周过热 → 清仓
    ("overheat", "downtrend"):             "strong_sell",
    ("overheat", "strong_uptrend"):        "sell",
    ("overheat", "weak_golden"):           "sell",
    ("overheat", "range"):                 "watch_sell",
    ("overheat", "pullback_entry"):        "watch_sell",           # 周过热 + 日回踩 → 防钓底
    ("overheat", "left_entry"):            "deep_rally_exit",
    ("overheat", "insufficient"):          "avoid",                # 周过热 + 数据不足 → 不评估

    # ── weekly = insufficient（数据不足，保守中立）─────────────────────────
    ("insufficient", "*"):                 "hold",
}
```

### 新旧矩阵对比

> 命中数 = 该档位在 8×8 矩阵中（不含默认兜底）的显式命中条数。

| 档位 | 旧命中数 | 新命中数 | 变化 |
|---|---|---|---|
| strong_buy | 4 | 3 | 双周共振（pullback/strong × pullback/strong） |
| buy | 2 | 2 | 周看多 + 日反弹/左侧 |
| watch_buy | 4 | 2 | 周买 + 日整理/假金叉 |
| deep_pullback_entry | 1 | 1 | 保留 |
| light_buy | 7 | 7 | 周中性/强 + 日有信号 |
| hold | 0 | ~18 | 中央态（含 insufficient 兜底行） |
| watch | ~23 | 0 | 全部迁移为 hold 或 avoid |
| watch_sell | 0 | 10 | 新增：周弱/假金叉 + 日未确认走坏 |
| light_sell | 0 | 1 | 新增：周平 + 日过热 |
| sell | 0 | 6 | 新增：周弱 + 日已弱 |
| strong_sell | 0 | 4 | 双周共振死叉/过热 → 清仓 |
| deep_rally_exit | 0 | 5 | 周弱 + 日强反弹 → 离场窗口 |
| avoid | 26+ | 5 | 仅数据不足 / 双周假弱等兜底（不评估） |

---

## 5. 综合分对称加成

买侧正加成、卖侧负加成、hold 为零、avoid 沉底：

```python
_SCORE_BONUS: dict[str, float] = {
    "strong_buy":   8,
    "buy":          4,
    "deep_pullback_entry": 2,
    "light_buy":    2,
    "watch_buy":    +1,   # 偏多观察，略上浮
    "hold":         0,    # 真中性
    "watch_sell":   -1,   # 偏空观察，略下沉
    "light_sell":   -2,
    "deep_rally_exit": -2,
    "sell":         -4,
    "strong_sell":  -8,
    "avoid":       -99,
}
```

综合分 = 0.6 × 周线分 + 0.4 × 日线分 + 加成，裁剪到 [0, 100]。镜像对的分差：极对 16 分、主对 8 分、深层/轻层对 4 分、观察对 2 分——用户可见的排序距离。观察档的方向区分主要靠 base（周线好则 base 高），±1 是方向性确认、让同 base 票按"观察买 > 持有 > 观察卖"排开。

---

## 6. 前端改动

### 6.1 `frontend/src/pages/Scoreboard/constants.ts` 的 `COMBINED_PALETTE`

键名、颜色与后端 `_STAGE_META` 对齐：删除 `watch`，新增 `hold / light_sell / watch_sell / deep_rally_exit / sell / strong_sell`。加注释标明与后端同步。`COMBINED_PALETTE` 现有 icon 字段一并移除（前端不需要 emoji 徽标）。

### 6.2 Badge 渲染

ScoreRow / CombinedView / CombinedDetailView 都引用 `COMBINED_PALETTE[stage]`，不改渲染逻辑、只换调色板即全局生效。若渲染处用了 `icon` 字段需同步移除。

### 6.3 侧向过滤

`ScoreboardToolbar` 的档位过滤增加两组：

- 买侧：strong_buy + buy + watch_buy + deep_pullback_entry + light_buy
- 卖侧：light_sell + watch_sell + deep_rally_exit + sell + strong_sell

---

## 7. 迁移与兼容

### 7.1 DB 迁移

`stock_score_combined.combined_stage` 是 TEXT 列，无 schema 变更。存量行语义由一次 force 重扫自然覆盖：

- `watch` → 按新规则落入 hold 或 avoid（无需手工处理）
- `avoid` → 语义保留不变
- 买侧档位名不变

**无需迁移逻辑**，一次 force 重扫即可走完。

### 7.2 测试用例

`backend/tests/test_combined_stage.py` 中断言 `watch` 的地方需同步改为新档位名（多为 `hold` / `avoid`）。

### 7.3 文案同步

- `ScoreCriteriaModal.tsx`：评分标准弹窗的档位列表换成新档位
- `combined_judge.py` 的 `_STAGE_META` 全部重写
- `ScoreDetail.tsx` 腿详情自动用新调色板

---

## 8. 风险与缓解

| 风险 | 缓解 |
|---|---|
| watch → hold 迁移期间 UI 偶发无状态显示 | 前端 `COMBINED_PALETTE` 暂留 `watch` 键映射到 hold，运行 1 个月后再删 |
| 卖侧颗粒度太多、用户分不清进出时机 | 提供“买侧 / 卖侧”分段过滤视图，默认隐藏卖侧 |
| 对称加成导致负分过多 | watch_sell 起始为 -1，前期保持买侧权重略高（±8 vs ±4 已是对称） |
| deep_rally_exit 难理解 | 详情卡片显示公式：周弱 + 日反弹 = 离场窗口 |

---

## 9. 实施顺序

| # | 步骤 | 修改文件 | 预估 |
|---|---|---|---|
| 1 | 新决策矩阵 + `_SCORE_BONUS` + `_STAGE_META` | `backend/app/features/combined_judge.py` | +120 行 |
| 2 | `combined_stage` 默认回退从 watch 改 hold | 同上 | 1 行 |
| 3 | 后端测试同步新档位名 | `backend/tests/test_combined_stage.py` | ~50 行 |
| 4 | 前端 `COMBINED_PALETTE` 重写（去 icon）+ 侧过滤 | `constants.ts` + `ScoreboardToolbar.tsx` 等 | ~120 行 |
| 5 | 文案弹窗更新 | `ScoreCriteriaModal.tsx` / `ScoreDetail.tsx` | ~30 行 |
| 6 | force 重扫填充新档位 | 运行期 | — |
| 7 | 观察 1 周期后 commit / tag v1.4.0 | — | — |

---

## 10. 完整闭环

```
未持仓                    已持仓
买侧 (5档) → hold ←→ 卖侧 (5档) → strong_sell → 回到 hold（等再次信号）
              ↑
              hold（持有 / 观察，等方向）
avoid（系统不评估：数据不足 / 双周假弱，不入仓位维度）
       ↓（数据补全 / 信号出现）
     重入 hold
```

至此：买 5 档、持有 1 档、卖 5 档、场外 1 档，双不动点对称系统下，进入 / 持有 / 退出全部有唯一归属。

---

# 附录 A：全状态与文本对照表

## A.1 单腿趋势状态 trend_stage（8 档）

| 枚举值 | 前端徽章 | 后端 reason 文案（现状） | 触发条件（决策树） | 操作建议 |
|---|---|---|---|---|
| `pullback_entry` | 可入手（红） | 金叉态·上方空间足，可入手 | 金叉 + 历史可靠或未过热有空间 | 可入手 |
| `left_entry` | 左侧·轻仓（紫） | 死叉态·下跌动能衰竭（下跌过峰），高风险左侧机会·轻仓 | 死叉 + 底部过峰强档 + 历史分≥64 | 轻仓左侧埋伏，逆势高风险 |
| `strong_uptrend` | 上升趋势（深红） | 金叉态·强趋势已涨，可持有·不追高·逢高减 | ADX≥25 + 已涨一段 + 无顶部过峰 | 持有，不追高，逢高减 |
| `weak_golden` | 弱势金叉（橙） | 金叉态·动能掉头（上涨过峰），别追等回踩 | 金叉 + 顶部过峰或动能走弱 | 别追，等回踩 |
| `overheat` | 过热（橙） | 金叉态但贴上轨（短期过热），等回踩 | %B>1.10 且 ADX<25，或 %B>0.85 非强趋势 | 等回踩，勿追高 |
| `range` | 震荡（蓝） | 观望（等金叉或信号不明） | 其余一切：金叉贴下轨 / 死叉历史尚可等 | 观望 |
| `downtrend` | 下跌趋势（绿） | 死叉态·历史金叉延续差，回避 | 深跌历史差 / 距高点近 / 死叉历史差 | 回避 |
| `insufficient` | 数据不足（灰） | 历史数据不足（需 ≥60 根日线） | K 线 < 60 根 | 等数据积累 |

## A.2 过峰信号状态 peak_signal（6+2 种）

| 枚举值 | 象限 | 触发条件 | 消费路径 |
|---|---|---|---|
| `上涨过峰` | 水上（dif>0）+ slope 向上 | acc_z < -1 或红柱缩 | peak_top：拦金叉追入 + exclude_up 过滤 |
| `顶部回落` | 水上 + slope 向下 | acc_z > +1 或绿柱回升 | peak_top：拦金叉追入（死叉时落入 range/downtrend） |
| `下跌过峰` | 水下 + slope 向下 | acc_z > +1 或绿柱回升 | peak_bot：喂 left_entry |
| `底部反转` | 水下 + slope 向上 | acc_z < -1 或红柱缩 | peak_bot：喂 left_entry |
| `涨势延续` | 任意 + 无触发 | 不满足触发条件 | 纯展示，conf=0 |
| `跌势延续` | 任意 + 无触发 | 不满足触发条件 | 纯展示，conf=0 |
| `顶部回落`（旧语义，废弃） | — | — | 仅供旧 DB 数据兼容 |

> 置信度 0-100：基础分（bar 触发 15 / acc 触发 25 / 双触发 45）+ 量能加成（缩量 0 / 中性 15 / 放量 30）。强档阈值：daily 51 / weekly 40。

## A.3 MACD 信号状态 current_state（6 种）

| 枚举值 | 含义 | 判定 |
|---|---|---|
| `金叉·走强` | 金叉 + DIF 加速向上 | current_golden=True 且 slope>0 |
| `金叉·走弱` | 金叉但动能掉头 | current_golden=True 且 slope<0 |
| `死叉·修复` | 死叉 + 绿柱回升 | current_golden=False 且 slope>0 |
| `死叉·走弱` | 死叉继续恶化 | current_golden=False 且 slope<0 |
| `金叉` | 裸金叉（slope 无数据） | current_golden=True 且 slope=None |
| `死叉` | 裸死叉（slope 无数据） | current_golden=False 且 slope=None |

## A.4 综合档位 combined_stage：现状 7 档 → 新方案 12 档

### 现状（7 档）

| 档位 | 中文 | 动作 | 分数加成 |
|---|---|---|---|
| strong_buy | 强买信号 | 重仓买入 | +8 |
| buy | 买入 | 可买入 | +4 |
| watch_buy | 观察买 | 加自选盯日线 | 0 |
| deep_pullback_entry | 深度回踩 | 轻仓分批 | +2 |
| light_buy | 轻仓试 | 轻仓试仓 | +2 |
| watch | 观望 | 不动 | 0 |
| avoid | 回避 | 回避 | -99 |

### 新方案（12 档）

| 档位 | 中文 | 仓位动作 | 分数加成 | reason（示意） |
|---|---|---|---|---|
| strong_buy | 强买信号 | 重仓买入 | +8 | 日周线同向看多共振，最强入场信号 |
| buy | 买入 | 可买入 | +4 | 周线看好 + 日线已反弹 |
| deep_pullback_entry | 深度回踩 | 轻仓分批 | +2 | 周趋势内日线超跌回踩，回调入场机会 |
| watch_buy | 观察买 | 先盯 | +1 | 周看多但日线还整理，等升级 |
| light_buy | 轻仓试 | 轻仓 | +2 | 周中性 + 日线有起涨信号 |
| hold | 持有 | 不动 | 0 | 可交易但无明确方向，等信号升级 |
| light_sell | 轻仓减 | 减仓 | -2 | 周走弱但日未确认走坏，先减风险 |
| watch_sell | 观察卖 | 先盯 | -1 | 周定调偏坏，日线确认后升级减仓 |
| deep_rally_exit | 反弹离场 | 分批减仓 | -2 | 周已走坏，日反弹是离场窗口 |
| sell | 卖出 | 中大仓减 | -4 | 日周均走坏，尽快出清 |
| strong_sell | 强卖信号 | 清仓 | -8 | 双周共振走弱，最强离场信号 |
| avoid | 场外回避 | 不介入 | -99 | 系统不评估（数据不足/双周假弱），无操作指令 |

### 新旧映射

| 旧档位 | 新档位去向 |
|---|---|
| strong_buy / buy / watch_buy / deep_pullback_entry / light_buy | 名称不变 |
| watch | 按 (weekly, daily) 组合 → hold 或 avoid |
| avoid | 语义保留（label 改“场外回避”更准确） |

---

# 附录 B：实现参考（现状代码锚点）

- 决策矩阵：`backend/app/features/combined_judge.py` 的 `_MATRIX` / `_STAGE_META` / `_SCORE_BONUS`
- 单腿决策树：`backend/app/features/trend_judge.py` 的 `judge_trend` / `_REASONS`
- 过峰特征：`backend/app/features/scoring/peak.py` 的 `_peak_features`
- MACD 状态：`backend/app/features/scoring/golden.py` 的 `current_state`
- 前端调色板：`frontend/src/pages/Scoreboard/constants.ts` 的 `STAGE_PALETTE` / `COMBINED_PALETTE`
