# AI Stock Lens

个人自用的 A 股技术分析工作台：本地部署，AI 多视角分析 + MACD 金叉打分 + 统一操作指示。

## 它做什么

**AI 分析**：牛熊辩论（综合）/ 反量化 / 反身性三视角并行，Trader Agent 给出带价位/仓位/止损的统一操作清单；个股对话带全上下文，SSE 流式输出。

**选股打分**：综合分 = 0.70·金叉延续性 + 0.20·波段适配 + 0.10·股息。**日线/周线/日周综合** 三视图切换——weekly 看方向、daily 定时机，综合页 **12 档对称状态机**（买侧 5 档 strong_buy/buy/watch_buy/deep_pullback_entry/light_buy + 中央 hold + 卖侧 5 档 watch_sell/light_sell/deep_rally_exit/sell/strong_sell + 场外 avoid），详情页给「当前已涨 / 剩余中位预期 / 剩余平均预期」三维可预期涨幅。趋势状态机 8 态驱动决策（pullback_entry 可入手 / left_entry 左侧轻仓 …），过峰信号四象限 + 0-100 置信度分级（按周期校准）。

**自选管理**：多对多分组 + 批量加入/移出 + 乐观刷新（操作与提示同步变）。全 A 元数据内置（5550 条 A 股随版本打包，ETF/新股由远程兜底补齐），添加股票联想秒出。

## 一键安装（Windows，无需 Docker / 命令行）

1. 到 [Releases](https://github.com/xinyue-cres/ai-stock-lens/releases) 下载 `AI-Stock-Lens-win.zip`
2. 解压到你自己的目录（**别放 C:\Program Files**）
3. 双击 `AI-Stock-Lens.exe`，浏览器自动打开就能用；关闭黑色窗口 = 退出

首次使用：右上角 ⚙ 填 AI Key 才能用 AI 分析；**不填也能用** K 线、指标、选股打分。数据存在 exe 旁 `data/`；首启动从内置全 A 元数据种子初始化，打开就能秒搜。

遇到 "Windows 已保护你的电脑" 提示 → 点"更多信息"→"仍要运行"（未买签名证书属正常）。

## 用 Docker 启动（熟悉技术）

```bash
cp backend/.env.example backend/.env   # 填 AI_API_KEY（OpenAI 兼容协议，默认 DeepSeek）
docker compose up -d
open http://localhost:8080
```

本地开发：

```bash
cd backend && source .venv/bin/activate && uvicorn app.main:app --reload --port 8000
cd frontend && pnpm install && pnpm dev
```

## 技术栈

| 层 | 技术 |
|---|---|
| 后端 | Python 3.12 · FastAPI · SQLModel · SQLite |
| 数据源 | AKShare（东财/新浪/腾讯）· BaoStock |
| AI | OpenAI 兼容协议（默认 DeepSeek） |
| 前端 | React 18 · Vite · TypeScript · Ant Design · TanStack Query |
| 部署 | Windows 可执行版（PyInstaller）· Docker Compose |

## 项目结构

```
ai-stock-lens/
├── backend/
│   ├── run.py                  # Windows 可执行版入口（自动开浏览器）
│   ├── seed.sqlite             # 打包内置：全 A 元数据种子库（随版本提交，本地重建）
│   └── app/
│       ├── ai/                 # prompts/ + normalizers + analyzer
│       ├── api/                # FastAPI 路由；api/score/ 打分路由包
│       ├── datasource/         # 多源 fallback router（东财→BaoStock→新浪→腾讯）
│       ├── schemas/            # score_components：components_json 单一解析点
│       ├── features/
│       │   ├── scoring/        # 打分引擎包（golden/peak/band/engine/rates）
│       │   ├── trend_judge.py    # 趋势状态机（8 态决策树）
│       │   ├── combined_judge.py # 日周合并评判（12 档对称矩阵）
│       │   └── timeframe.py      # 日/周 bar 重采样 + sigma 折换
│       ├── indicators/         # 技术指标引擎（含 dif_slope_series）
│       ├── models/             # SQLModel 数据模型
│       ├── db/                 # 引擎 + get_session + migrations + seed 拆包
│       └── services/
│           ├── scan/           # 打分扫描包（state/pool/kline_cache/writer/runner）
│           ├── snapshot_service.py # 同步后快照刷新 + turnover 补算
│           └── ...             # analysis/signals/trader/sync/stock 等业务层
├── frontend/src/
│   ├── api/                    # HTTP 层（一文件一领域）
│   ├── pages/                  # StockList / StockDetail / Scoreboard / Positions / Compare / SyncLogs
│   │   └── */hooks/ + */components/  # 页面级 hook 与组件分离（容器只留编排）
│   └── features/               # analysis 分析工作台 / watchlist / settings / status-bar
├── docs/                       # state-machine-redesign.md 状态机设计
├── packaging/                  # PyInstaller spec
└── .github/workflows/          # Windows 自动构建 + Release
```
