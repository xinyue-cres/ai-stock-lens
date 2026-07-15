# 个人个股技术分析工具 · 方案设计

> 版本：v0.1（MVP 设计）
> 日期：2026-07-14
> 定位：个人自用、本地部署、局域网访问的 A 股技术分析工具

---

## 1. 目标与非目标

### 1.1 目标
- 服务**个人**看盘、复盘、决策辅助，非商用、非多用户
- 仅对**交易数据**做分析：K 线、均线、成交量、换手率、量比、经典技术指标、价格形态、资金流、相对强弱
- 提供**AI 生成的技术面分析报告与操作倾向建议**（观察/关注/规避一类的语义标签，不做自动下单）
- 覆盖 20–80 只自选股，日频更新，每日收盘后同步一次

### 1.2 非目标（明确不做）
- 不做基本面分析（财报、估值、行业对比等）
- 不做实时行情、Level-2、分钟级 tick 数据（可作为后续扩展）
- 不做自动化交易、条件单下发
- 不做多用户、账号系统、权限体系
- 不做公网访问（暂时），局域网即可

---

## 2. 核心用户故事

| 编号 | 故事 | 优先级 |
|---|---|---|
| US-1 | 打开单股分析页，输入或选择一只股票，即时看到 K 线 + 全套技术指标叠加 | P0 |
| US-2 | 页面上点"生成 AI 分析"按钮，AI 综合所有指标输出一段技术面报告 + 操作倾向标签 | P0 |
| US-3 | 每日收盘后系统自动同步自选股日线数据，无需手动触发 | P0 |
| US-4 | 打开"信号扫描"页，看到今天自选股中触发了哪些预设信号（金叉、放量突破、形态达成等） | P1 |
| US-5 | 打开"多股对比"页，把几只自选股的走势/相对强弱/阶段涨幅并排看 | P2 |
| US-6 | 手机在同一局域网下访问，也能看到 K 线和分析报告 | P1 |

---

## 3. 技术架构

### 3.1 总体架构图（文字版）

```
┌─────────────────────────────────────────────────────────────┐
│                     浏览器（PC / 手机）                       │
│           React + TradingView lightweight-charts             │
└──────────────────────────┬──────────────────────────────────┘
                           │  HTTP (局域网 IP:PORT)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI (Python)                          │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ REST API │ │  Indicator│ │  AI 分析 │ │ 定时任务       │   │
│  │  Routes  │ │  Engine   │ │  Client  │ │ APScheduler    │   │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └───────┬────────┘   │
│       │            │            │                │            │
│       ▼            ▼            ▼                ▼            │
│  ┌────────────────────────────────────────────────────────┐  │
│  │           DataSource 抽象层（Provider 模式）             │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │  │
│  │  │ AKShare  │ │ efinance │ │ Tushare  │ │ BaoStock │  │  │
│  │  │  (主)    │ │  (预留)   │ │  (预留)  │ │  (预留)  │  │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘  │  │
│  └────────────────────────────────────────────────────────┘  │
│                           │                                   │
│                           ▼                                   │
│                    ┌──────────────┐                          │
│                    │ SQLite (本地) │                          │
│                    └──────────────┘                          │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
                 ┌───────────────────┐
                 │  DeepSeek API     │
                 │  （OpenAI 兼容）   │
                 └───────────────────┘
```

### 3.2 部署形态
- **一台家用电脑**（Mac/Linux 均可）作为服务器，24×7 常开或按需开
- 通过 **Docker Compose** 一键启动，两个服务：`backend`（FastAPI）+ `frontend`（Nginx 静态托管 React 构建产物）
- 局域网内任意设备（手机/平板/其他电脑）通过 `http://<主机IP>:<端口>` 访问

---

## 4. 技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| 后端语言 | Python 3.11+ | 数据/量化/AI 生态最完整 |
| Web 框架 | FastAPI | 自动 OpenAPI 文档、异步友好、类型注解 |
| 数据源（主） | AKShare | 免费、无需注册、内含东财/新浪/雪球数据 |
| 数据源（备） | efinance / Tushare / BaoStock | 预留 Provider 位，MVP 不启用 |
| 指标计算 | numpy + pandas（自行实现） | 依赖少，指标逻辑透明可调 |
| 存储 | SQLite（`data/app.db`） | 20–80 只票 × 若干年日线，SQLite 绰绰有余；无需服务化 |
| ORM | SQLModel（SQLAlchemy + Pydantic） | 类型友好，模型即 schema |
| 定时任务 | APScheduler | 内嵌在 FastAPI 进程，无需额外服务 |
| AI SDK | `openai` Python SDK（OpenAI 兼容模式） | DeepSeek / 通义 / 智谱皆兼容此协议，切换只改 `base_url` + `model` |
| 前端框架 | React 18 + Vite + TypeScript | 生态成熟、Vite 启动快 |
| K 线图 | lightweight-charts（TradingView 官方开源） | 专业交易图形观感、轻量、性能好 |
| 前端 UI 组件 | Ant Design | 中文场景友好、表格/表单开箱即用 |
| 前端数据流 | TanStack Query | 简化后端数据获取与缓存 |
| 容器化 | Docker + Docker Compose | 一键起停、隔离依赖 |

---

## 5. 数据模型（SQLite）

### 5.1 表结构

```
stock                          -- 股票基础信息
├── code           TEXT PK     -- 如 "600519"
├── name           TEXT        -- 如 "贵州茅台"
├── market         TEXT        -- "SH" / "SZ" / "BJ"
├── is_watchlist   BOOLEAN     -- 是否为自选股
└── added_at       DATETIME

kline_daily                    -- 日线数据
├── code           TEXT
├── trade_date     DATE
├── open           REAL
├── high           REAL
├── low            REAL
├── close          REAL
├── volume         INTEGER     -- 手
├── amount         REAL        -- 元
├── turnover       REAL        -- 换手率 %
├── pct_chg        REAL        -- 涨跌幅 %
└── PRIMARY KEY (code, trade_date)

capital_flow_daily             -- 资金流（后续启用 efinance/东财时）
├── code           TEXT
├── trade_date     DATE
├── main_net       REAL        -- 主力净流入（元）
├── super_large    REAL
├── large          REAL
├── medium         REAL
├── small          REAL
└── PRIMARY KEY (code, trade_date)

sync_log                       -- 同步任务日志
├── id             INTEGER PK
├── started_at     DATETIME
├── finished_at    DATETIME
├── status         TEXT        -- "success" / "failed" / "partial"
├── stocks_synced  INTEGER
└── error_msg      TEXT

ai_report                      -- AI 分析报告缓存（避免重复调用）
├── id             INTEGER PK
├── code           TEXT
├── as_of_date     DATE        -- 报告对应的截止交易日
├── model          TEXT        -- "deepseek-chat" 等
├── report_md      TEXT        -- Markdown 全文
├── verdict        TEXT        -- 结构化倾向标签："bullish"/"neutral"/"bearish"/"caution"
├── created_at     DATETIME
└── UNIQUE (code, as_of_date, model)
```

### 5.2 数据保留策略
- 日线数据：全量保留，20–80 只 × 10 年 ≈ 20 万行以内，SQLite 秒查
- AI 报告：按 `(code, date, model)` 唯一缓存，同一天同一模型的报告只算一次

---

## 6. 后端模块设计

### 6.1 目录结构

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI 入口，含 lifespan 启动定时任务
│   ├── config.py               # 环境变量加载（AI Key、数据源开关）
│   ├── db.py                   # SQLModel engine + session
│   ├── models/                 # 数据模型
│   │   ├── stock.py
│   │   ├── kline.py
│   │   ├── capital_flow.py
│   │   └── ai_report.py
│   ├── datasource/             # 数据源 Provider
│   │   ├── base.py             # DataSource 抽象基类
│   │   ├── akshare_provider.py # 主实现
│   │   ├── efinance_provider.py# 预留占位
│   │   ├── tushare_provider.py # 预留占位
│   │   └── baostock_provider.py# 预留占位
│   ├── indicators/             # 指标计算
│   │   ├── ma.py               # MA5/10/20/60/120/250 + 排列形态
│   │   ├── oscillators.py      # MACD/KDJ/RSI/BOLL
│   │   ├── volume.py           # 量比、换手、量能形态
│   │   ├── patterns.py         # 高低点、突破、经典形态
│   │   ├── strength.py         # 相对强弱 RS
│   │   └── engine.py           # 一站式计算入口，输入 DataFrame → 输出 dict
│   ├── ai/
│   │   ├── client.py           # OpenAI-兼容客户端封装
│   │   ├── prompts.py          # 提示词模板
│   │   └── analyzer.py         # 组装指标 → 调 AI → 结构化返回
│   ├── scheduler.py            # APScheduler 任务定义
│   ├── services/               # 业务服务层
│   │   ├── stock_service.py
│   │   ├── sync_service.py     # 增量/全量同步
│   │   └── analysis_service.py # 单股分析、信号扫描
│   └── api/                    # 路由
│       ├── stocks.py
│       ├── watchlist.py
│       ├── analysis.py
│       ├── signals.py
│       └── sync.py
├── data/                       # SQLite 与日志
│   └── app.db
├── tests/
├── pyproject.toml              # 用 uv 或 pip 均可
├── Dockerfile
└── .env.example
```

### 6.2 DataSource 抽象

```python
# datasource/base.py
class DataSource(Protocol):
    name: str

    def get_stock_list(self) -> list[StockInfo]: ...

    def get_daily_kline(
        self, code: str, start: date, end: date, adjust: Literal["", "qfq", "hfq"] = "qfq"
    ) -> pd.DataFrame: ...

    def get_capital_flow(self, code: str, start: date, end: date) -> pd.DataFrame | None: ...
```

- MVP 只实现 `AkshareProvider`
- 其他 Provider 保留文件与类定义但 `raise NotImplementedError`

### 6.3 指标引擎输出契约（`indicators/engine.py`）

```python
def compute_all(df: pd.DataFrame) -> dict:
    return {
        "ma": {"ma5": ..., "ma10": ..., "arrangement": "多头/空头/纠缠"},
        "macd": {"dif": ..., "dea": ..., "hist": ..., "cross": "gold"|"death"|None},
        "kdj":  {...},
        "rsi":  {...},
        "boll": {...},
        "volume": {"turnover": ..., "vol_ratio": ..., "volume_pattern": "放量突破"|...},
        "patterns": ["突破 20 日新高", "跌破 60 日均线", ...],
        "rs":   {"vs_index": 0.83, "rank_pct": 0.72},
        "latest_price": {...},
    }
```

- 返回的每个字段都可直接喂给 AI 提示词或前端展示

### 6.4 API 契约（MVP）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` | 健康检查 |
| GET | `/api/stocks/search?q=茅台` | 模糊查股票（本地 + 数据源兜底） |
| GET | `/api/watchlist` | 自选股列表 |
| POST | `/api/watchlist` | 新增自选股 `{code}` |
| DELETE | `/api/watchlist/{code}` | 移除自选股 |
| GET | `/api/stocks/{code}/kline?start=&end=&adjust=qfq` | 日线 + 指标合并 |
| POST | `/api/stocks/{code}/ai-report` | 生成/取缓存 AI 分析 `{as_of_date?}` |
| GET | `/api/signals/today` | 今日自选股信号扫描（P1） |
| POST | `/api/sync/run` | 手动触发同步 |
| GET | `/api/sync/logs?limit=20` | 同步历史 |

### 6.5 定时任务
- 每交易日 16:00（可配置）触发 `sync_service.sync_watchlist()`：
  1. 遍历 `is_watchlist=true` 的股票
  2. 每只票增量拉最新 K 线（从库中最后一天 + 1 到今天）
  3. 写入 `kline_daily`
  4. 记录 `sync_log`
- 非交易日跳过（用 `chinese_calendar` 或 AKShare 交易日历判断）

---

## 7. 前端模块设计

### 7.1 目录结构

```
frontend/
├── index.html
├── vite.config.ts
├── package.json
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/                    # 调用后端
│   │   ├── client.ts           # axios 实例
│   │   ├── stocks.ts
│   │   ├── watchlist.ts
│   │   ├── analysis.ts
│   │   └── sync.ts
│   ├── pages/
│   │   ├── StockDetail/        # 单股分析页（MVP 核心）
│   │   │   ├── index.tsx
│   │   │   ├── KLineChart.tsx  # lightweight-charts 封装
│   │   │   ├── IndicatorPanel.tsx
│   │   │   └── AIReport.tsx
│   │   ├── Watchlist/          # 自选股管理
│   │   ├── Signals/            # 信号扫描（P1）
│   │   └── Compare/            # 多股对比（P2）
│   ├── components/
│   ├── hooks/
│   ├── types/
│   └── utils/
├── Dockerfile
└── nginx.conf                  # 生产静态托管
```

### 7.2 单股分析页布局（MVP）

```
┌─────────────────────────────────────────────────────────┐
│  股票搜索栏  [ 贵州茅台 (600519.SH) ▼ ]  [同步] [生成分析] │
├─────────────────────────────────────────────────────────┤
│                                                          │
│                    K 线主图 + MA/BOLL 叠加                │
│                                                          │
│  ────────────────────────────────────────────────────    │
│                    成交量副图 + 量比副图                    │
│  ────────────────────────────────────────────────────    │
│                    MACD 副图                              │
│  ────────────────────────────────────────────────────    │
│                    KDJ / RSI 副图（Tab 切换）              │
├─────────────────────────────────────────────────────────┤
│  指标面板：均线排列 / 量能形态 / 突破形态 / RS 排名 …       │
├─────────────────────────────────────────────────────────┤
│  AI 分析报告：                                            │
│  【倾向：观察】                                            │
│  当前 MA5/10/20 呈多头排列，成交量温和放大 …               │
└─────────────────────────────────────────────────────────┘
```

---

## 8. AI 集成设计

### 8.1 客户端封装
- 走 OpenAI 兼容协议：
  - DeepSeek：`base_url=https://api.deepseek.com/v1`，`model=deepseek-chat`
  - 通义千问：`base_url=https://dashscope.aliyuncs.com/compatible-mode/v1`
  - 智谱：`base_url=https://open.bigmodel.cn/api/paas/v4`
- 从 `.env` 读取：`AI_PROVIDER` / `AI_API_KEY` / `AI_BASE_URL` / `AI_MODEL`

### 8.2 提示词结构（`prompts.py`）
- **System**：设定角色为"资深 A 股技术分析师，仅基于交易数据做判断，不涉及基本面/消息面，输出结构化 + 中文"
- **User** 内容按结构塞入：
  1. 股票基本信息（代码、名称、市场）
  2. 最近 N 日（默认 60）K 线摘要
  3. 指标引擎输出的 dict（JSON 序列化）
  4. 用户可选："关注短线（5-20 日）"或"关注中线（20-60 日）"
- **输出契约**（用 JSON mode 或 structured output）：

```json
{
  "verdict": "bullish | neutral | bearish | caution",
  "confidence": 0.0-1.0,
  "summary": "一句话总结",
  "report_md": "详细 Markdown 报告",
  "key_signals": ["MA 多头排列", "量能温和放大", ...],
  "risks": ["跌破 60 日均线将走弱", ...]
}
```

### 8.3 免责与幻觉抑制
- 每份报告结尾自动附加固定免责声明
- 提示词中明确禁止编造未出现的指标值，只能引用输入中的字段
- 报告页 UI 明显标注"AI 生成，非投资建议"

---

## 9. 部署与运维

### 9.1 Docker Compose

```yaml
services:
  backend:
    build: ./backend
    volumes:
      - ./backend/data:/app/data     # SQLite 持久化
    env_file: ./backend/.env
    ports:
      - "8000:8000"
    restart: unless-stopped

  frontend:
    build: ./frontend
    ports:
      - "8080:80"
    depends_on: [backend]
    restart: unless-stopped
```

### 9.2 启动流程
```bash
cd ai-stock-lens
cp backend/.env.example backend/.env      # 填 AI key
docker compose up -d
open http://localhost:8080                # 或 http://<内网IP>:8080
```

### 9.3 局域网手机访问
- Mac 上查 IP：`ipconfig getifaddr en0`
- 手机浏览器打开 `http://<IP>:8080`
- 若 Mac 防火墙拦截，需允许 Docker/8080 入站

### 9.4 数据备份
- 每周把 `backend/data/app.db` 复制到 iCloud/OneDrive 目录（或用 cron 脚本）
- 一份 `.db` 文件即完整备份，恢复直接拷回

---

## 10. 实现顺序（分阶段交付）

### Phase 0 · 骨架搭建（当前）
1. 目录结构 + `docker-compose.yaml` + `Dockerfile ×2` + `.env.example`
2. 后端 FastAPI 空壳：`/api/health` 可返回 `{"status": "ok"}`
3. 前端 React 空壳：Vite + AntD + 一个空的"单股分析页"路由
4. SQLModel 定义所有表 + 首次启动自动建表
5. AKShare Provider 骨架（`get_daily_kline` 单只票能返回 DataFrame）
6. `docker compose up` 能起来，前后端联通

### Phase 1 · 单股分析页 MVP（P0）
1. 搜索/选择股票 → 拉日线 → 存 SQLite（首次全量、后续增量）
2. 指标引擎完整实现：MA / MACD / KDJ / RSI / BOLL / 量能 / 形态 / RS
3. 前端 K 线主图 + 副图 + 指标面板
4. `AI 分析` 按钮跑通：调 DeepSeek → 存 `ai_report` → 前端渲染
5. 自选股增删

### Phase 2 · 自动化（P0/P1）
1. APScheduler 定时任务：每交易日 16:00 同步自选股
2. `/api/sync/run` 手动触发 + 前端"同步"按钮
3. `/api/signals/today` 信号扫描
4. 前端信号扫描页

### Phase 3 · 多股对比（P2）
1. 多股 RS 排名视图
2. 阶段涨幅对比表
3. 走势归一化叠加图

---

## 11. 风险与已知取舍

| 风险 | 缓解 |
|---|---|
| AKShare 依赖第三方站点，偶发接口失效 | Provider 抽象层，可切换到 efinance/Tushare |
| AI 输出可能有幻觉/过度自信 | JSON schema 约束 + 提示词禁止编造 + 前端明显免责 |
| 家用电脑关机则服务中断 | 明确非 24×7 需求；下班后当天数据已同步完成 |
| 数据同步超时/失败 | `sync_log` 记录 + 前端展示 + 手动重跑按钮 |
| pandas-ta 与 numpy 新版兼容 | 锁定 requirements 版本 |

---

## 12. 环境变量清单（`backend/.env.example`）

```dotenv
# --- AI ---
AI_PROVIDER=deepseek                                # deepseek | qwen | zhipu
AI_API_KEY=your_key_here
AI_BASE_URL=https://api.deepseek.com/v1
AI_MODEL=deepseek-chat

# --- 数据源 ---
DATASOURCE_PRIMARY=akshare                          # akshare | efinance | tushare | baostock
TUSHARE_TOKEN=                                      # 可选

# --- 同步 ---
SYNC_ENABLED=true
SYNC_CRON_HOUR=16
SYNC_CRON_MINUTE=10

# --- 应用 ---
APP_LOG_LEVEL=INFO
DB_PATH=/app/data/app.db
```

---

## 13. 后续可能扩展（不在 MVP）
- 分钟线支持（AKShare `stock_zh_a_hist_min_em`）
- 回测模块（backtrader 集成）
- 龙虎榜 / 游资活跃度
- 大盘/板块环境指标（作为 AI 输入的上下文）
- Web 端登录鉴权 + Cloudflare Tunnel 公网化
- 结构化"AI 决策日记"（把每次报告和后续实际走势对比复盘）
