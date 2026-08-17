# AI Stock Lens · 架构设计

> 版本：v3.1
> 更新：2026-08-17
> 定位：个人自用、本地部署的 A 股多视角 AI 技术分析工作台

---

## 1. 目标与非目标

### 目标
- 个人看盘、复盘、决策辅助，日频更新
- 仅对交易数据做分析：K 线、均线、成交量、换手率、技术指标、形态、资金流
- **多视角 AI 分析**：牛熊辩论（综合）、反量化、反身性三个独立视角
- **统一操作指示**：Trader Agent 消费多视角报告 → 输出可执行动作清单
- **个股对话**：基于已有分析上下文自由问答
- 覆盖 20–80 只自选股，每交易日收盘后自动同步
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
┌────────────────────────────────────────────────────────────────┐
│                    浏览器（React + Ant Design）                  │
│                                                                │
│  ┌─ 列表页 (/) ─────────────────────────────────────────────┐ │
│  │  [GroupNav]  [SummaryBar] [Toolbar] [StockRow×N]          │ │
│  │  (悬浮左)    [BatchActionBar] (悬浮右)                     │ │
│  └───────────────────────────────────────────────────────────┘ │
│  ┌─ 详情页 (/stock/:code) ──────────────────────────────────┐ │
│  │  [Sidebar]  │  [AI分析] [操作指示] [K线] [日志] [指标] [对话]│ │
│  └─────────────┴─────────────────────────────────────────────┘ │
└──────────────────────────┬─────────────────────────────────────┘
                           │ HTTP / SSE
                           ▼
┌────────────────────────────────────────────────────────────────┐
│                    FastAPI (Python 3.12)                        │
│                                                                │
│  ┌─────────────────── AI 层 ───────────────────────┐           │
│  │ ai/prompts/  (按 Agent 分文件)                  │           │
│  │   bull_bear.py · quant.py · reflexivity.py      │           │
│  │   trader.py · chat.py · _common.py              │           │
│  │ ai/normalizers.py · ai/analyzer.py              │           │
│  └─────────────────────────────────────────────────┘           │
│                                                                │
│  ┌─────── Services ─────────────────────────────────────────┐  │
│  │ analysis_service  (K线加载 + 指标计算 + AI 输入构建)     │  │
│  │ signals_service   (列表聚合 + stance/verdict/times map)  │  │
│  │ trader_service    (操作指示生成)                          │  │
│  │ sync_service      (数据同步调度)                          │  │
│  │ market_service    (大盘数据)                              │  │
│  │ stock_service     (自选 CRUD + group_ids)                │  │
│  │ position_service  (持仓)                                 │  │
│  │ chat_service · review_service · settings_service         │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ┌─── DataRouter ───────────────┐  ┌─── 指标引擎 ─────────┐  │
│  │ EastMoney → BaoStock → Sina  │  │ MA/BOLL/MACD/RSI/KDJ │  │
│  │ → Tencent (fallback+熔断)    │  │ 量能/形态/强度/周线   │  │
│  └──────────────────────────────┘  │ signals 信号扫描      │  │
│                                     └──────────────────────┘  │
│  ┌─── SQLite ───────┐  ┌─── APScheduler ───┐                 │
│  │ stock/stock_group │  │ 每交易日 16:10     │                 │
│  │ kline_daily       │  │ 自动同步自选股     │                 │
│  │ ai_report         │  └────────────────────┘                 │
│  │ position/setting  │                                         │
│  └───────────────────┘                                         │
└────────────────────────────────────────────────────────────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │ OpenAI 兼容 API       │
               │ (DeepSeek/通义/智谱)  │
               └───────────────────────┘
```

---

## 3. 前端架构

### 3.1 目录结构

```
frontend/src/
├── App.tsx                 # 路由 + 顶部导航
├── api/                    # HTTP 层（一文件一领域：score/compare/positions/sync/...）
├── hooks/                  # 全局共享 hooks
│   └── useSignalsQuery     # signals-today (列表+侧栏共享)
├── shared/                 # 纯工具 (theme, timeAgo)
├── pages/
│   ├── StockList/          # 首页列表（含分组/批量操作）
│   ├── StockDetail/        # 详情页
│   ├── Scoreboard/         # 选股打分页（趋势状态机排行 + AI 点评/汇总）
│   ├── Positions/          # 持仓页
│   ├── Compare/            # 对比页
│   └── SyncLogs/           # 同步日志
└── features/
    ├── stock-context/      # 当前股票 context（仅 code 管理）
    ├── analysis/           # 详情页分析功能
    │   ├── hooks/          # useAiReport, useStockAnalysis
    │   ├── panels/         # panelRegistry + 6 个 Tab 面板
    │   ├── ai/             # AI 报告子组件
    │   ├── action-plan/    # 操作指示子组件
    │   ├── indicators/     # 指标条 + 大盘条
    │   ├── kline/          # K 线图
    │   └── chat/           # 对话面板
    ├── watchlist/          # 详情页左栏 sidebar
    ├── settings/           # 设置抽屉
    └── status-bar/         # 顶部状态栏
```

### 3.2 路由与导航

```
/              → StockListPage (全宽列表 + 悬浮分组/批量面板)
/stock/:code   → StockDetail   (左栏 sidebar + 右栏分析 Tabs)
/scoreboard    → Scoreboard    (选股打分排行 + 趋势状态机)
/positions     → Positions     (持仓管理)
/compare       → Compare       (多股对比)
/sync          → SyncLogs
```

- 列表页 → 详情页：携带 `?group=N` 保持分组上下文
- 详情页左栏只显示当前分组内的股票
- 返回列表时恢复分组选中状态

### 3.3 状态管理

- **TanStack Query**：所有服务端状态（报告/指标/持仓/信号）
- **useSignalsQuery**：唯一的 signals-today query 源，列表页和侧栏共享
- **mutationKey 共享**：跨组件同步 AI 生成的 loading 状态
- **URL searchParams**：分组筛选持久化（刷新保留）
- **批量任务状态**：页面级 state + per-item Map 传递给 StockRow

### 3.4 面板注册

```typescript
// panelRegistry.ts — 声明式数组，加面板 = 加一行
const registry: PanelDef[] = [
  { id: 'ai-report',   label: 'AI 分析',   order: 10, Component: AiReportPanel },
  { id: 'action-plan', label: '操作指示', order: 15, Component: ActionPlanPanel },
  ...
]
```

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

| Service | 职责 | 行数 |
|---------|------|------|
| `analysis_service` | K 线加载 + 指标计算 + 缓存 + AI 输入构建 | ~150 |
| `signals_service` | 列表信号聚合 + stance/verdict/report-times 批量查询 | ~200 |
| `trader_service` | 操作指示生成编排 | ~100 |
| `sync_service` | 数据同步（全量/增量/指数/冷却） | ~150 |
| `market_service` | 大盘指数同步 + 市场摘要 | ~120 |
| `stock_service` | 自选 CRUD + group_ids JSON 读写 | ~140 |
| `position_service` | 持仓 CRUD + 盈亏计算 | ~80 |
| `scoring_service` | 选股扫描编排（拉 K 线→打分→趋势判断→upsert）+ 进度/取消 | ~300 |

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

纯计算层，无 AI 参与、无 I/O，位于 `features/stock_scorer.py` + `features/trend_judge.py`，
由 `scoring_service` 在扫描时驱动。

**综合分**：`0.70·金叉延续性 + 0.20·波段适配 + 0.10·股息`
- **金叉延续性**（核心）：纯历史统计——金叉后能否涨一大段、不反复横跳。
  `0.60·金叉后大段上涨`（周期内峰值涨幅，均值/中位各半，开方×10 放大低分区分度）+ `0.40·金叉寿命`
  （延续达标率 + 快速反叉惩罚 + 方差惩罚）。
- **波段适配**：`sigma_20d` 适中最佳（三角归一，锚点 2~7% 峰 4%）× MA5 下方平均停留天数（节奏）。
- **股息**：近 3 年平均股息率（个股）/ 中性 50（ETF/LOF）。

**趋势状态机（8 态）**：`trend_judge.py::_decide_stage` 是纯决策函数（无 I/O，可单测）。
金叉态（DIF > DEA）→ 上升候选，死叉态 → 左侧/下跌/观望。

| 枚举 | 标签 | can_entry | 语义 |
|---|---|---|---|
| `pullback_entry` | 可入手 | ✅ 安全 | 金叉态·回踩/刚启动·历史可靠 |
| `left_entry` | 左侧机会 | ✅ 高风险 | 死叉态·下跌过峰·历史尚可·轻仓 |
| `strong_uptrend` | 上升趋势 | ❌ 持有 | 金叉态·ADX 强·已涨一段·可持有不追高逢高减 |
| `weak_golden` | 弱势金叉 | ❌ | 金叉态·动能掉头（上涨过峰/走弱）·别追 |
| `overheat` | 过热 | ❌ | 贴上轨（%B>0.85）·非强趋势 |
| `downtrend` | 下跌趋势 | ❌ | 死叉·高位刚死叉·或历史差 |
| `range` | 震荡 | ❌ | 观望（贴下轨/胜率不足/信号不明） |
| `insufficient` | 数据不足 | ❌ | 数据 <60 根 |

**两层可入手**：`can_entry` 保持布尔字段（`pullback_entry` 与 `left_entry` 都算 True），
两档区分由前端按 `trend_stage` 判断——`left_entry` 用紫色系 +「左侧·轻仓」⚠ 提示，明确高风险逆势。

**过峰信号评级**：`_peak_features` 用 `bar`（柱缩/柱回升）× `acc_z`（动能二阶导 z-score）触发，
按「触发类型（bar 15 / acc 25 / 双 45）+ 量能（缩 0 / 中 15 / 放 30）」产出 `peak_conf` 0-100 五档
（极弱≤20 / 弱21-35 / 中36-50 / 强51-65 / 极强≥66）。**强档以上（≥51）才进决策树降级**，
弱/中档只做前端提示（避免误伤涨势中正常柱缩）。

**关键阈值**（经验值，可数据校准）：
`_SIGNAL_RELIABLE=72`（金叉延续可靠线）、`_LEFT_ENTRY_SIGNAL=64`（左侧专用低线，慢牛弱势股天然分低）、
`_ADX_STRONG=25`（强趋势）、`_STRONG_TREND_GAIN=8%`（强趋势"已涨一段"）、`_PEAK_CONF_STRONG=51`（过峰强档）。

**K 线历史窗口**：`config.scan_kline_bars = 1000`（≈ **4 年**，覆盖完整牛熊周期，避免 2 年窗口只含
2024-09 起的单边牛市）；`scan_kline_days = 1000 × 1.5 = 1500 自然日`（1.4 只够 ~960 交易日，会致
缓存覆盖判定永远不足）。扫描优先读库内缓存（单连接串行，SQLite WAL 多连接并发慢 8.7 倍），
≥ `1000 × 0.9` 根命中，未命中才并发网络拉取（`scan_concurrency=12`）。

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
| `stock` | 基础信息 + is_watchlist + group_ids(JSON) + note |
| `stock_group` | 分组定义 (name, sort_order) |
| `kline_daily` | 日线 OHLCV + turnover + pct_chg |
| `ai_report` | AI 报告 (horizon: combined/anti_quant/reflexivity/action_plan) |
| `ai_report_review` | 报告复盘评分 |
| `position` | 持仓 (quantity, cost_price, opened_at) |
| `app_setting` | 应用配置 (AI config / total_capital) |
| `stock_score` | 选股打分结果（综合分 + 组件明细 + trend_stage/can_entry） |
| `capital_flow_daily` | 资金流数据（对比/分析用） |
| `stock_dividend` | 个股股息数据 |
| `sync_log` | 同步日志 |

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
  POST /score/scan → scoring_service（手动触发，仅扫描不落 K 线库）
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
| GET | `/api/score/list` | 打分排行（sort/scope/group/peak_filter 过滤） |
| GET | `/api/score/{code}` | 单只打分明细 |
| POST | `/api/score/trend/{code}` | 趋势判断（独立调用 judge_trend） |
| POST | `/api/score/scan` | 触发扫描（scope/codes/force/group_ids） |
| GET/POST | `/api/score/scan/status` | 扫描进度轮询 / 取消 |
| POST | `/api/score/summarize` | AI 整组汇总 |
| POST | `/api/score/analyze-batch` | AI 逐股点评 |

---

## 9. 部署

### Docker Compose

```yaml
services:
  backend:
    build: ./backend
    volumes: [./backend/data:/app/data]
    env_file: ./backend/.env
    ports: ["8000:8000"]

  frontend:
    build: ./frontend
    ports: ["8080:80"]
    depends_on: [backend]
```

### 本地开发

```bash
# 后端
cd backend && source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && pnpm dev
```

---

## 10. 已知技术债

| 项目 | 影响 | 优先级 |
|------|------|--------|
| `stock.group_id` 废弃字段 | 无功能影响，占空间 | 低 |
| 自选信号扫描逐股票 load_kline_df | 已优化记忆体复用 + 单连接缓存读；80 只仍可能 2-3s | 中 |
| Toolbar 19 个 props | 可读性差 | 低 |
| 对话历史仅 sessionStorage | 关页丢失 | 设计决策 |
| 趋势状态机阈值（ADX/涨幅/胜率）为经验值 | 上线后可据此前的数据回放校准 | 中 |

---

## 11. 明确不做的事

- 交易流水 / 多账户 / 撮合
- 实时报价 / 盘中 push
- 基本面 / 行业对比
- 公网访问 / 多用户认证
- 回测框架
