# AI Stock Lens

个人自用的 A 股技术分析工作台。本地部署，AI 多视角分析 + 统一操作指示 + 个股对话。

## 功能概览

### AI 多视角分析
- **综合分析**（牛熊辩论）：牛派/熊派并行 → 裁判裁决，输出 verdict/scenarios/signals/risks
- **反量化分析**：量化模拟器 + 散户反向策略，识别机构行为模式
- **反身性分析**：索罗斯反身性框架，判断正/负反馈循环阶段

### Trader 操作指示
- 消费三份分析报告 + 技术指标 + 持仓，输出统一执行清单
- 3-6 条优先级排序的操作动作（含触发价位/仓位/止损/目标价/risk_reward）
- 按 scenario_type 分桶：进攻组 / 防守组 / 观察组
- 当前禁止事项（command + invalidation 格式的纪律命令）
- 资金感知的仓位建议（A 股 100 股最小单位）

### 个股对话
- 选中股票后自由提问，AI 自动注入该股全部分析上下文
- SSE 流式输出，Markdown 渲染
- sessionStorage 持久化（刷新保留，关浏览器清空）

### 数据源
- DataRouter fallback 链：东财 → BaoStock → 新浪 → 腾讯
- 支持 A 股 + 场内基金（ETF/LOF），基金走 fund_etf_hist_sina 独立通道
- Provider 级熔断：连续 3 次失败 → 300s 冷却
- 腾讯 snapshot 60s 缓存，盘后快速可用

### 其他
- 技术指标引擎（MA/BOLL/MACD/RSI/ATR/KDJ/量能/形态/周线）
- 持仓管理（手动录入，浮盈计算）
- K 线图（TradingView lightweight-charts）
- 分析日志（历史报告查看）
- 定时同步（每交易日 16:10 自动更新）
- 数据源健康度监控

## 快速开始

```bash
# 1. 配置
cp backend/.env.example backend/.env
# 填入 AI_API_KEY（DeepSeek/通义/智谱等 OpenAI 兼容协议）

# 2. Docker 启动
docker compose up -d

# 3. 访问
open http://localhost:8080
```

### 本地开发

```bash
# 后端
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload --port 8000

# 前端
cd frontend
pnpm install
pnpm dev
```

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 · FastAPI · SQLModel · SQLite |
| 数据源 | AKShare（东财/新浪/腾讯）· BaoStock |
| AI | OpenAI 兼容协议（默认 DeepSeek） |
| 前端 | React 18 · Vite · TypeScript · Ant Design · TanStack Query |
| 部署 | Docker Compose · Nginx |

## 项目结构

```
ai-stock-lens/
├── backend/
│   └── app/
│       ├── ai/              # prompts/ + normalizers + analyzer + client
│       ├── api/             # FastAPI 路由 (signals, analysis, action_plan, ...)
│       ├── datasource/      # 多源 provider + fallback router
│       ├── features/        # 量化因子计算
│       ├── indicators/      # 技术指标引擎
│       ├── models/          # SQLModel 数据模型
│       └── services/        # 业务逻辑层
│           ├── analysis_service   (K线 + 指标 + AI输入)
│           ├── signals_service    (列表聚合 + 状态查询)
│           ├── trader_service     (操作指示)
│           ├── sync_service       (数据同步)
│           └── ...
├── frontend/
│   └── src/
│       ├── api/             # HTTP 层 (一文件一领域)
│       ├── hooks/           # 全局共享 hooks (useSignalsQuery)
│       ├── shared/          # 工具 (theme, timeAgo)
│       ├── pages/
│       │   ├── StockList/   # 首页列表 (index + 6 子组件)
│       │   └── StockDetail/ # 详情页
│       └── features/
│           ├── analysis/    # 分析功能 (hooks + panels + ai + action-plan)
│           ├── stock-context/  # 当前股票 context
│           ├── watchlist/   # 详情页左栏 sidebar
│           └── settings/    # 设置
└── docker-compose.yaml
```
