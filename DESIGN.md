# AI Stock Lens · 架构设计

> 版本：v3.0
> 更新：2026-07-20
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
├── api/                    # HTTP 层（一文件一领域）
├── hooks/                  # 全局共享 hooks
│   └── useSignalsQuery     # signals-today (列表+侧栏共享)
├── shared/                 # 纯工具 (theme, timeAgo)
├── pages/
│   ├── StockList/          # 首页列表
│   │   ├── index.tsx       # 组合逻辑 (~170行)
│   │   ├── constants.ts    # 类型 + 常量
│   │   └── components/     # SummaryBar, Toolbar, StockRow,
│   │                       # GroupNav, BatchActionBar, GroupManagerModal
│   ├── StockDetail/        # 详情页
│   ├── Positions/          # 持仓页
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
/positions     → Positions
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
| signals N+1 (逐股票 load_kline_df) | 26 只~1s，80 只可能 3s+ | 中 |
| Toolbar 19 个 props | 可读性差 | 低 |
| 对话历史仅 sessionStorage | 关页丢失 | 设计决策 |

---

## 11. 明确不做的事

- 交易流水 / 多账户 / 撮合
- 实时报价 / 盘中 push
- 基本面 / 行业对比
- 公网访问 / 多用户认证
- 回测框架
