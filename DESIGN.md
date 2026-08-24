# AI Stock Lens · 架构设计

> 版本：v3.4
> 更新：2026-08-24（v1.3.1 之后文档对齐：weekly/combined/元数据种子/调度默认关/fs 重构）
> 定位：个人自用、本地部署的 A 股多视角 AI 技术分析工作台

---

## 1. 目标与非目标

### 目标
- 个人看盘、复盘、决策辅助，日频更新
- 仅对交易数据做分析：K 线、均线、成交量、换手率、技术指标、形态、资金流
- **多视角 AI 分析**：牛熊辩论（综合）、反量化、反身性三个独立视角
- **统一操作指示**：Trader Agent 消费多视角报告 → 输出可执行动作清单
- **个股对话**：基于已有分析上下文自由问答
- 覆盖 20–80 只自选股；同步/复盘定时任务**默认全关**（`SYNC_ENABLED=false`，手动点同步为主；环境变量置 true 才恢复每交易日 16:10 自动同步）
- **分组管理**：多分组（多对多），支持批量 AI 分析 / 操作指示

### 非目标
- 不做基本面分析（财报、估值）
- 不做实时行情、分钟级数据
- 不做自动化交易、条件单
- 不做多用户、权限
- 不做公网访问

---

## 2. 系统架构

```
浏览器（React + Ant Design）
  ├─ 列表页 (/)          GroupNav · Toolbar · StockRow · BatchActionBar
  ├─ 详情页 (/stock/:code)  Sidebar + AI分析/操作指示/K线/指标/对话 Tabs
  └─ 打分页 (/scoreboard)   打分排行（日/周/综合 三视图）
        │ HTTP / SSE
        ▼
FastAPI (Python 3.12)
  ├─ AI 层：ai/prompts/（bull_bear·quant·reflexivity·trader·chat）+ normalizers + analyzer
  ├─ Services：analysis · signals · trader · sync · market · stock · position · chat · review
  ├─ features/：scoring 打分包 · trend_judge 决策树 · combined_judge 合并评判 · timeframe 周期层
  ├─ DataRouter：EastMoney → BaoStock → Sina → Tencent（fallback + 熔断）
  ├─ APScheduler：定时任务默认全关（SYNC_ENABLED=false）
  └─ SQLite：stock/stock_group/kline_daily/ai_report/position/setting/stock_score*/sync_log
        │
        ▼
     OpenAI 兼容 API（DeepSeek/通义/智谱）
```

---

## 3. 前端架构

### 3.1 目录结构

```
frontend/src/
├── api/         # HTTP 层（一文件一领域）
├── hooks/       # useSignalsQuery（signals-today，列表+侧栏共享）/ useInvalidation / global state
├── shared/      # 纯工具 (theme, timeAgo)
├── pages/       # StockList / StockDetail / Scoreboard / Positions / Compare / SyncLogs
│   └── Scoreboard/hooks/  # useScoreboardData · useScoreboardActions（页面=布局组装）
├── features/    # analysis(详情 Tabs) · watchlist · settings · status-bar
└── stock-context # 当前股票 code context
```

### 3.2 路由与导航

```
/              → StockListPage (列表 + 悬浮分组/批量面板)
/stock/:code   → StockDetail   (左栏 sidebar + 右栏分析 Tabs)
/scoreboard    → Scoreboard    (打分排行 + 日/周/综合 三视图 + AI 点评)
/positions     → Positions     (持仓管理)
/compare       → Compare       (多股对比)
/sync          → SyncLogs
```

列表页 → 详情页携带 `?group=N` 保持分组上下文；返回时恢复选中。

### 3.3 状态管理

- **TanStack Query**：所有服务端状态
- **useSignalsQuery**：signals-today 唯一 query 源，列表页和侧栏共享
- **mutationKey 共享**：跨组件同步 AI 生成 loading
- **URL searchParams**：分组筛选/选中股票持久化（刷新/分享保留）
- **乐观刷新**：分组操作 `qc.setQueryData` 即时更新缓存，列表与 toast 同步
- **批量任务状态**：页面级 state + per-item Map 传给 StockRow

### 3.4 面板注册

`panelRegistry.ts` 声明式数组，新增详情页 Tab 面板 = 加一行配置。

---

## 4. 后端架构

### 4.1 分层

```
api/           → 路由层（薄 controller，参数校验 + 调用 service）
services/      → 业务逻辑层（数据编排、缓存、查询聚合）
ai/            → AI 调用层（prompt 管理、LLM 调用、输出解析）
indicators/    → 纯计算层（无 IO，给一份 DataFrame 返回指标 dict）
datasource/    → 数据源适配层（多源 fallback + 熔断）
models/        → 数据模型（SQLModel）
```

### 4.2 Service 职责划分

v1.2 重构：`services/scoring_service.py`(599行 god object) 拆为 `services/scan/` 包，
`features/stock_scorer.py`(605行) 拆为 `features/scoring/` 包，公开接口保持不变（re-export shim）。

| Service / 包 | 职责 | 结构 |
|---------|------|------|
| `analysis_service` | K 线加载 + 指标计算 + 缓存 + AI 输入构建 | 单文件 |
| `signals_service` | 列表信号聚合 + stance/verdict/report-times 批量查询 | 单文件 |
| `trader_service` | 操作指示生成编排 | 单文件 |
| `sync_service` | 数据同步（全量/增量/指数/冷却） | 单文件 |
| `market_service` | 大盘指数同步 + 市场摘要 | 单文件 |
| `stock_service` | 自选 CRUD + group_ids JSON 读写 + 全 A 元数据搜索 | 单文件 |
| `position_service` | 持仓 CRUD + 盈亏计算 | 单文件 |
| `services/scan/` | 打分扫描编排 | `state`(进度) `pool`(候选池) `kline_cache`(缓存/新鲜度) `writer`(upsert) `runner`(编排) |

### 4.3 features 包结构

```
features/
├── scoring/           # 打分引擎包（v1.2 拆分自 stock_scorer.py）
│   ├── rates.py       # 权重 + 阈值/周期校准常量（SIGMA_SCALE/_PEAK_CONF_STRONG_BY_TF）
│   ├── base.py        # _norm/_tri 工具
│   ├── golden.py      # 金叉延续性：post_gain + life_score + cycle_stats + signal_summary
│   ├── peak.py        # _peak_features 过峰信号（四象限标签 + 置信度分级）
│   ├── band.py        # _band_score（幅度+节奏、含 timeframe 折换）+ _dividend_score
│   └── engine.py      # compute_indicator_cache（指标快照复用）+ score_stock 总编排
├── trend_judge.py     # 8 态决策树（金叉/死叉 驱动）
├── combined_judge.py  # 日周合并：28 态矩阵 → 7 档 combined_stage + combined_score
└── timeframe.py       # to_bars（日→周五收盘周重采样）+ SIGMA_SCALE 注册表
```

---

## 5. AI 多 Agent 设计

### 5.1 综合分析（牛熊辩论）

```
输入（指标 + K 线摘要）
  → Bull Agent ──┐
                  ├─→ Judge Agent：裁决 verdict + scenarios
  → Bear Agent ──┘
```

- Bull/Bear 并行调用（ThreadPoolExecutor）
- Judge 产出：verdict / confidence / tradability / evidence_review / scenarios
- 弱证据约束：支持 <3 条时 confidence ≤ 0.4
- scenarios 带 `scenario_type`（entry/add/trim/stop_loss/take_profit/observe）

### 5.2 反量化分析

```
输入（量化因子 + 大盘状态）
  → Quant Simulator：机构量化策略画像
  → Anti-Quant Agent：散户反向策略
```

- `crowding_level`：low / medium / high / extreme
- `trap_risk`：false_breakout / crowded_chase / stop_loss_cascade / none
- crowding_level=low 时不得强行逆向

### 5.3 反身性分析

单次调用：判断索罗斯反身性周期阶段
- 输出：reflexivity_stage / narrative / feedback_loop / scenarios
- 约束：必须绑定可观察指标，禁止纯心理描述

### 5.4 Trader Agent（操作指示）

```
输入 = 三份报告精简版 + 当前指标 + 持仓 + 总资金
  → 排序/去重/仓位化
  → 输出：overall_stance + actions[] + bias_checks + conflicts
```

- 每条 action 带 stop_loss + target_price + risk_reward
- bias_checks：纪律命令（禁止追高/破位必走等）
- A 股 100 股最小交易单位 + 资金感知

### 5.5 个股对话

- 基于已有报告上下文回答问题
- SSE 流式输出
- sessionStorage 持久化

### 5.6 选股打分与趋势状态机（features 层）

纯计算层，无 AI 参与、无 I/O。v1.2 起拆为 `features/scoring/` 包（golden/peak/band/engine/rates/base），
`features/trend_judge.py` 决策树独立，`services/scan/` 包在扫描时驱动。

**综合分**：`0.70·金叉延续性 + 0.20·波段适配 + 0.10·股息`
- **金叉延续性**（核心）：纯历史统计——金叉后能否涨一大段、不反复横跳。
  `0.60·金叉后大段上涨`（周期内峰值涨幅，均值/中位各半，开方×10 放大低分区分度）+ `0.40·金叉寿命`
  （延续达标率 + 快速反叉惩罚 + 方差惩罚）。
- **波段适配**：`sigma_20d` 适中最佳（三角归一，锚点 2~7% 峰 4%）× MA5 下方平均停留天数（节奏）。
  **周期折换**：weekly/monthly 把原始 sigma 除以 `SIGMA_SCALE`（weekly 实测 ×2.56，200 只 A 股校准）
  折回日等效再喂锚，保证跨周期打分分布对齐。
- **股息**：近 3 年平均股息率（个股）/ 中性 50（ETF/LOF）。

**日线 / 周线双周期（v1.1）**：`features/timeframe.py` 的 `to_bars(df, tf)` 把日线重采样为周五收盘周 bar
（`W-FRI` anchor，open=首/high=max/low=min/close=尾/volume·amount=sum）。打分/趋势判断全部以 bar
为单位运算、不感知 K 线粒度；`_MIN_ROWS=60` 两周期同义（60 bar）。
`stock_score` 复合主键 `(code, scan_timeframe)`，daily/weekly 各占一行互不覆盖。

**日周综合评判（v1.2）**：`features/combined_judge.py`——按状态矩阵把 (weekly_stage, daily_stage)
合并成 7 档 `combined_stage`：`strong_buy / buy / deep_pullback_entry / light_buy / watch_buy / watch / avoid`。
- 周线=方向层（该不该碰），日线=时机层（什么时候进）；
- 综合分 = `0.6·weekly_total + 0.4·daily_total + 阶段加成`（strong_buy+8 / buy+4 / deep/light+2 / avoid-99）；
- **strong_buy 位置约束**：双腿 pct_b 任一 ≥0.8 则降级 buy（历史 fwd5 数据显示 0.5-0.8 是
  最佳入场 sweet spot），降级原因存 `demote_reason` 并在详情页黄条显示；
- 详情页三维可预期涨幅：`当前已涨（weekly signal_gain_pct）/ 剩余中位 / 剩余平均预期
  （hist_golden_peak_median / pct − 已涨）`。

**趋势状态机（8 态）**：`trend_judge.py::_decide_stage` 是纯决策函数（无 I/O，可单测）。
金叉态（DIF > DEA）→ 上升候选，死叉态 → 左侧/下跌/观望。

| 枚举 | 标签 | can_entry | 语义 |
|---|---|---|---|
| `pullback_entry` | 可入手 | ✅ 安全 | 金叉态·回踩/刚启动·历史可靠 |
| `left_entry` | 左侧机会 | ✅ 高风险 | 死叉态·下跌过峰·历史尚可·轻仓 |
| `strong_uptrend` | 上升趋势 | ❌ 持有 | 金叉态·ADX 强·已涨一段·可持有不追高逢高减 |
| `weak_golden` | 弱势金叉 | ❌ | 金叉态·动能掉头（上涨过峰/走弱）·别追 |
| `overheat` | 过热 | ❌ | 贴上轨（%B>1.10）且 ADX 弱（强趋势 momentum breakout 豁免）；%B>0.85 且非强趋势 |
| `downtrend` | 下跌趋势 | ❌ | 死叉·高位刚死叉·或历史差 |
| `range` | 震荡 | ❌ | 观望（贴下轨/胜率不足/信号不明） |
| `insufficient` | 数据不足 | ❌ | 数据 <60 根 |

**两层可入手**：`can_entry` 保持布尔字段（`pullback_entry` 与 `left_entry` 都算 True），
两档区分由前端按 `trend_stage` 判断——`left_entry` 用紫色系 +「左侧·轻仓」⚠ 提示，明确高风险逆势。

**过峰信号评级**：`_peak_features` 用 `bar`（柱缩/柱回升）× `acc_z`（动能二阶导 z-score）触发，
按「触发类型（bar 15 / acc 25 / 双 45）+ 量能（缩 0 / 中 15 / 放 30）」产出 `peak_conf` 0-100 五档
（极弱≤20 / 弱21-35 / 中36-50 / 强51-65 / 极强≥66）。**强档以上才进决策树降级**，
弱/中档只做前端提示（避免误伤涨势中正常柱缩）。
**周期校准阈值**（`_PEAK_CONF_STRONG_BY_TF`）：daily=51 / weekly=40——weekly acc_z 分布系统性偏低
（44 个 candidate 全部 <51），沿用 daily 阈值会永远无 left_entry/overheat 触发。

**关键阈值**（经验值，可数据校准）：
`_SIGNAL_RELIABLE=72`（金叉延续可靠线）、`_LEFT_ENTRY_SIGNAL=64`（左侧专用低线，慢牛弱势股天然分低）、
`_ADX_STRONG=25`（强趋势）、`_STRONG_TREND_GAIN=8%`（强趋势"已涨一段"）、
`pct_b>1.10 + ADX<25`（过热线，强趋势豁免）。

**K 线历史窗口**：`config.scan_kline_bars = 1000`（≈ **4 年**，覆盖完整牛熊周期，避免 2 年窗口只含
2024-09 起的单边牛市）；`scan_kline_days = 1000 × 1.5 = 1500 自然日`（1.4 只够 ~960 交易日，会致
缓存覆盖判定永远不足）。扫描优先读库内缓存（单连接串行，SQLite WAL 多连接并发慢 8.7 倍），
≥ `1000 × 0.9` 根命中，未命中才并发网络拉取（`scan_concurrency=6`，12+ 会触发东财 rate limit）。
**盘中放宽（intraday_relax）**：15:00 前扫描时"昨日收盘"视为最新，grace 自动 +1，
避免全候选池被误判 stale 触发无效网络补拉。

---

## 6. 数据层

### 6.1 数据源 DataRouter

```python
stock_chain = [EastMoney, BaoStock, Sina, Tencent]
index_chain = [EastMoney, Sina]
```

- 熔断：连续 3 次失败 → 300s 冷却
- ETF/LOF 支持：代码前缀路由
- 换手率自动推算（缺失时从历史反推 float_shares）

### 6.2 数据模型

| 表 | 用途 |
|---|---|
| `stock` | 基础信息 + is_watchlist + group_ids(JSON) + note；**code 统一 6 位**（sina/东财 ETF 源前缀已清洗） |
| `stock_group` | 分组定义 (name, sort_order) |
| `kline_daily` | 日线 OHLCV + turnover + pct_chg |
| `ai_report` | AI 报告 (horizon: combined/anti_quant/reflexivity/action_plan) |
| `ai_report_review` | 报告复盘评分 |
| `position` | 持仓 (quantity, cost_price, opened_at) |
| `app_setting` | 应用配置 (AI config / total_capital) |
| `stock_score` | 选股打分结果；**复合主键 (code, scan_timeframe)**，daily/weekly 各占一行互不覆盖 |
| `stock_score_combined` | 日周合并评判结果（weekly/daily 双腿核心字段 + 7 档 combined_stage + demote_reason + hist_golden_peak_*/weekly_signal_gain_pct） |
| `capital_flow_daily` | 资金流数据（对比/分析用） |
| `stock_dividend` | 个股股息数据 |
| `sync_log` | 同步日志 |

### 6.3 分组设计

- 多对多通过 `stock.group_ids` JSON 数组实现（如 `[1,2]`）
- 避免 junction table 复杂度，适合个人规模
- 前端全量获取 + 本地筛选；批量「加入/移出分组」经 `PATCH /api/watchlist/{code}` 整体覆盖 group_ids
- v1.3 乐观刷新：分组操作后 `qc.setQueryData(['signals-today'])` 即时改缓存，列表与 toast 同步更新

### 6.6 全 A 元数据与种子库（v1.3）

- **本地 stock 表灌满全 A + ETF + LOF**（7569 条），搜索联想/添加永远不远程（2ms）；
- **code 统一 6 位清洗**（sina/东财 ETF 源返回 "sh600519"/"sz159998" 带前缀，直接入库会与业务 6 位 code 重复）；
- **拼音中间态不查远程**：拉丁字母且非数字（t/tia/tian'j）本地必然 miss，直接返回空——
  避免每键 10-30s 远程拉列打爆连接池（曾致 QueuePool 500）；
- **远程拉取互斥锁**：缓存未命中时并发请求经 `threading.Lock` 排队，只拉一次；
- **打包种子库 (`seed.sqlite`)**：CI 构建时预生成（约 1MB）随 exe 打进包，
  release 用户首启动 data/app.db 不存在时直接复制——首搜零等待。

### 6.3 分组设计

- 多对多通过 `stock.group_ids` JSON 数组实现（如 `[1,2]`）
- 避免 junction table 复杂度，适合个人规模
- 前端全量获取 + 本地筛选，保证分组切换时"全部"计数不变

---

## 7. 数据流

```
列表页:
  useSignalsQuery → GET /signals/today → signals_service.scan_watchlist_signals
                                           ├── load_kline_df (per stock)
                                           ├── _latest_stance_map (batch)
                                           ├── _latest_ai_verdict_map (batch)
                                           └── _latest_report_times_map (batch)

详情页:
  useStockAnalysis → GET /stocks/:code/kline → analysis_service.analyze
  useAiReport     → GET/POST /stocks/:code/ai-report → ai/analyzer
  useActionPlan   → GET/POST /stocks/:code/action-plan → trader_service

批量任务:
  batchRun(type, codes, concurrency=3)
    → type='ai': 每只股票 3 视角并行 (Promise.all)
    → type='action_plan': 每只股票 1 次
    → per-item 状态实时回传给 StockRow 展示

选股打分页 (Scoreboard):
  POST /score/scan → services/scan/runner（手动触发，仅扫描不落 K 线库）
     → 单连接串行读 K 线缓存（≥1000×0.9 根命中），未命中并发网络拉 ~1000 根
     → 每只 compute_indicator_cache → score_stock + judge_trend = StockScore（含 trend_stage）
     → 前端 GET /score/scan/status 轮询进度；GET /score/list 排行（按 peak_filter 过滤）
  GET /score/{code}      → 打分明细 + 趋势判断卡
  POST /score/trend/{code} → 独立 judge_trend（详情/工作台即算）
  POST /score/summarize · analyze-batch → AI 整组汇总 / 逐股点评
```

---

## 8. API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/signals/today` | 信号扫描 (列表数据源) |
| GET/POST/PATCH/DELETE | `/api/watchlist` | 自选股 CRUD + group_ids |
| GET/POST/PATCH/DELETE | `/api/groups` | 分组 CRUD |
| GET | `/api/market/summary` | 大盘摘要 (5min 冷却) |
| GET | `/api/stocks/search?q=` | 模糊搜索 |
| GET | `/api/stocks/{code}/kline` | K 线 + 指标 |
| POST | `/api/stocks/{code}/ai-report` | 生成 AI 报告 |
| POST | `/api/stocks/{code}/ai-report/all` | 一键三视角 |
| GET/POST | `/api/stocks/{code}/action-plan` | 操作指示 |
| POST | `/api/stocks/{code}/chat` | 对话 (SSE) |
| GET/POST/DELETE | `/api/positions` | 持仓 CRUD |
| POST | `/api/sync/run` | 同步全部 |
| POST | `/api/sync/stock/{code}` | 同步单只 |
| GET/PUT | `/api/settings/ai` | AI 配置 |
| GET/PUT | `/api/settings/capital` | 总资金 |
| GET | `/api/score/list` | 打分排行（sort/scope/group/peak_filter/timeframe 过滤） |
| GET | `/api/score/{code}` | 单只打分明细（timeframe 取双腿之一） |
| POST | `/api/score/trend/{code}` | 趋势判断（独立调用 judge_trend，timeframe 重采样） |
| POST | `/api/score/scan` | 触发扫描（scope/codes/force/group_ids/timeframe） |
| GET/POST | `/api/score/scan/status` | 扫描进度轮询 / 取消 |
| POST | `/api/score/summarize` | AI 整组汇总 |
| POST | `/api/score/analyze-batch` | AI 逐股点评 |
| GET | `/api/score/combined/list` | 日周合并评判列表（combined_stage/scope/group_ids/can_entry 过滤） |
| GET | `/api/score/combined/{code}` | 单只 combined 详情 |

---

## 9. 部署

```bash
# Docker（生产用）—— backend + frontend 服务，数据持久化到 ./backend/data
docker compose up -d
```

```bash
# 本地开发
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
cd frontend && pnpm dev
```

打包（Windows 可执行版）：`packaging/AI-Stock-Lens.spec`，CI（`.github/workflows/build-windows.yml`）
打 tag 自动构建 → Release。构建前跑 `backend/scripts/build_seed_db.py` 生成内置全 A 元数据种子库。

---

## 10. 已记录但未做的技术债

| 项目 | 影响 |
|------|------|
| `stock.group_id` 废弃字段 | 占空间，无功能影响 |
| 自选 signals 查询逐票 load_kline_df | 80 只 ~2s，可以二级缓存 |
| 阈值参数（信号可靠线 / ADX / 涨幅）为经验值 | 上线后可回放校准 |

---

## 11. 明确不做的事

- 交易流水 / 多账户 / 撮合
- 实时报价 / 盘中 push
- 基本面 / 行业对比
- 公网访问 / 多用户认证
- 回测框架
