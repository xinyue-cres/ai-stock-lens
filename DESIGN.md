# AI Stock Lens · 架构设计

> 版本：v2.0
> 更新：2026-07-16
> 定位：个人自用、本地部署的 A 股多视角 AI 技术分析工作台

---

## 1. 目标与非目标

### 目标
- 个人看盘、复盘、决策辅助，日频更新
- 仅对交易数据做分析：K 线、均线、成交量、换手率、技术指标、形态、资金流
- **多视角 AI 分析**：牛熊辩论、反量化、反身性三个独立视角
- **统一操作指示**：Trader Agent 消费多视角报告 → 输出可执行动作清单
- **个股对话**：基于已有分析上下文自由问答
- 覆盖 20–80 只自选股，每交易日收盘后自动同步

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
│  ┌──────────┬──────────┬──────┬──────┬──────┬────────┐        │
│  │ AI 分析  │ 操作指示 │ K 线 │ 日志 │ 指标 │  对话  │ (Tabs) │
│  └──────────┴──────────┴──────┴──────┴──────┴────────┘        │
└──────────────────────────┬─────────────────────────────────────┘
                           │ HTTP / SSE
                           ▼
┌────────────────────────────────────────────────────────────────┐
│                    FastAPI (Python 3.11)                        │
│                                                                │
│  ┌─────────────────── AI 层 ───────────────────────┐           │
│  │ BULL → BEAR → JUDGE (综合)                      │           │
│  │ QUANT_SIM → ANTI_QUANT (反量化)                 │           │
│  │ REFLEXIVITY (反身性)                             │           │
│  │ TRADER (操作指示：消费上述 + 指标 + 持仓)        │           │
│  │ CHAT (个股对话：注入上下文 + 流式)               │           │
│  └─────────────────────────────────────────────────┘           │
│                                                                │
│  ┌─────── 数据源 DataRouter ────────┐  ┌─── 指标引擎 ───┐     │
│  │ EastMoney → BaoStock → Sina → QQ │  │ MA/BOLL/MACD   │     │
│  │ (fallback + 熔断)                 │  │ RSI/KDJ/ATR    │     │
│  └───────────────────────────────────┘  │ 量能/形态/周线 │     │
│                                          └────────────────┘     │
│  ┌─── SQLite ───┐  ┌─── APScheduler ───┐                      │
│  │ kline_daily  │  │ 每交易日 16:10     │                      │
│  │ ai_report    │  │ 自动同步自选股     │                      │
│  │ position     │  └────────────────────┘                      │
│  │ stock        │                                              │
│  │ sync_log     │                                              │
│  └──────────────┘                                              │
└────────────────────────────────────────────────────────────────┘
                           │
                           ▼
               ┌───────────────────────┐
               │ OpenAI 兼容 API       │
               │ (DeepSeek/通义/智谱)  │
               └───────────────────────┘
```

---

## 3. AI 多 Agent 设计

### 3.1 综合分析（牛熊辩论）

Bull/Bear 并行 + Judge 串行：

```
输入（指标 + K 线摘要）
  → Bull Agent ──┐
                  ├─→ Judge Agent：裁决 verdict + scenarios
  → Bear Agent ──┘
```

- Bull/Bear 通过 ThreadPoolExecutor 并行调用，节省 ~50% 延迟
- 各 Agent 有独立 system prompt，禁止编造数据
- Judge 产出：verdict / confidence / scenarios / key_signals / risks / report_md
- 置信度校准：强制 0-1 区间，附带校准标尺约束

### 3.2 反量化分析

两次串行调用：

```
输入（量化因子 + 大盘状态）
  → Quant Simulator：模拟机构量化策略行为画像
  → Anti-Quant Agent：基于量化画像产出散户反向策略
```

### 3.3 反身性分析

单次调用：基于资金流/情绪指标判断索罗斯反身性周期阶段
- 输出：reflexivity_stage / narrative / feedback_loop / scenarios

### 3.4 Trader Agent（操作指示）

单次调用，消费所有上游：

```
输入 = 三份报告精简版 + 当前指标 + 持仓 + 总资金
  → 排序/去重/仓位化/个性化
  → 输出：overall_stance + actions[] + bias_checks + conflicts
```

核心规则：
- 不做新分析，只做执行层编排
- A 股 100 股最小交易单位
- 资金感知仓位建议
- bias_checks：do_not / do_instead 格式的散户偏差提醒
- confidence_adjustment：多视角冲突时的置信度折损

### 3.5 个股对话

```
用户消息 + 历史对话
  → (首轮) 注入全量上下文到 system prompt
  → (后续轮) 轻量 system + 对话历史
  → SSE 流式输出
```

- 不做新分析，基于已有报告回答问题
- sessionStorage 持久化（刷新保留，关浏览器清空）

---

## 4. 数据源设计

### DataRouter

```python
stock_chain = [EastMoney, BaoStock, Sina, Tencent]
index_chain = [EastMoney, Sina]
```

- Provider 抽象基类：`get_daily_kline()` / `get_index_daily()` / `get_stock_list()`
- **场内基金（ETF/LOF）支持**：代码前缀路由（51/56/58→SH, 15/16→SZ），通过 `fund_etf_hist_sina` 获取日线
- 基金代码在 BaoStock/腾讯中自动跳过（不支持），仅走东财/新浪
- 熔断机制：连续 3 次失败 → 300s 冷却 → 自动恢复
- 全链条失败返回空 DataFrame（不抛异常）
- 腾讯 Provider：60s snapshot 缓存，盘后 15:01 即可获取当日数据

### 换手率自动计算

当数据源缺少 turnover 时，从历史数据推算 float_shares：
```
float_shares = volume / (turnover / 100)  (取最近有值的一天)
missing_turnover = volume / float_shares * 100
```

---

## 5. 数据模型

| 表 | 用途 | 关键字段 |
|---|---|---|
| `stock` | 股票基础信息 | code(PK), name, market, is_watchlist |
| `kline_daily` | 日线数据 | code+trade_date(PK), OHLCV, turnover, pct_chg |
| `ai_report` | AI 报告缓存 | code, model, horizon, verdict, extras_json, created_at |
| `position` | 持仓 | code(unique), quantity, cost_price, opened_at |
| `sync_log` | 同步任务日志 | status, stocks_synced, error_msg |
| `app_setting` | 应用配置 | key(PK), value (AI config / total_capital) |

`ai_report.horizon` 枚举：`combined` / `anti_quant` / `reflexivity` / `action_plan`

---

## 6. 前端架构

### 面板注册系统

```typescript
registerPanel({ id: 'ai-report',   label: 'AI 分析',   order: 10 })
registerPanel({ id: 'action-plan', label: '操作指示', order: 15 })
registerPanel({ id: 'kline',       label: 'K 线',      order: 20 })
registerPanel({ id: 'diary',       label: '分析日志', order: 25 })
registerPanel({ id: 'indicators',  label: '指标详情', order: 30 })
registerPanel({ id: 'chat',        label: '对话',     order: 35 })
```

- Tabs 切换，`destroyInactiveTabPane` 节省内存
- 每个面板从 `useStock()` 获取当前 code，自包含

### 状态管理

- TanStack Query：服务端状态（报告/指标/持仓）
- `mutationKey` 共享模式：跨组件同步 loading 状态
- `useIsMutating`：组件重建后仍能感知 pending 请求

### 工作台布局

```
┌──────────────┬──────────────────────────────────────┐
│  自选股列表   │  KeyMetricsStrip (股票名+盘口指标)    │
│  (sticky)    ├──────────────────────────────────────┤
│  · 搜索      │  [AI分析] [操作指示] [K线] [日志] ... │
│  · 筛选      │                                      │
│  · item 列表 │  (当前激活 Tab 面板)                  │
│              │                                      │
└──────────────┴──────────────────────────────────────┘
```

---

## 7. API 一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/stocks/search?q=` | 模糊搜索 |
| GET/POST/DELETE | `/api/watchlist` | 自选股 CRUD |
| GET | `/api/stocks/{code}/kline` | K 线 + 指标 |
| POST | `/api/stocks/{code}/ai-report` | 生成 AI 报告 |
| POST | `/api/stocks/{code}/ai-report/all` | 一键生成三份 |
| GET/POST | `/api/stocks/{code}/action-plan` | 操作指示 |
| POST | `/api/stocks/{code}/chat` | 对话 (SSE) |
| GET/POST/DELETE | `/api/positions` | 持仓 CRUD |
| GET | `/api/signals/today` | 信号扫描 |
| POST | `/api/sync/run` | 手动同步 |
| GET | `/api/sync/status` | 调度器状态 |
| GET | `/api/sync/datasource-health` | 数据源健康度 |
| GET/PUT | `/api/settings/ai` | AI 配置 |
| GET/PUT | `/api/settings/capital` | 总资金设置 |

---

## 8. 部署

### Docker Compose

```yaml
services:
  backend:
    build: ./backend
    container_name: ai-stock-lens-backend
    volumes: [./backend/data:/app/data]
    env_file: ./backend/.env
    ports: ["8000:8000"]

  frontend:
    build: ./frontend
    container_name: ai-stock-lens-frontend
    ports: ["8080:80"]
    depends_on: [backend]
```

### 本地开发

```bash
# 后端
cd backend && source .venv/bin/activate
DB_PATH=data/app.db uvicorn app.main:app --reload --port 8000

# 前端
cd frontend && pnpm dev
```

---

## 9. 明确不做的事

- 交易流水表 / 多账户 / 撮合
- 实时报价 / 盘中 push 通知
- 对话历史持久化存储
- 基本面数据 / 行业对比
- 公网访问 / 多用户认证
- 回测框架

---

## 10. 演进锚点

以下为可能的未来方向，当前不做但保留接口：

- **Trader 交易剧本**：每日开盘前生成当日剧本（条件→动作映射）
- **持仓进阶**：分批加仓流水、分红/送股调整
- **盘中触发通知**：接入实时报价，action 条件命中时 push
- **复盘闭环**：用户 mark "已执行" → 下次生成时对比实际效果
- **大盘环境**：沪深300/创业板/涨停家数等作为 AI 上下文
