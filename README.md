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

### 选股打分
- 全 A 股 + ETF 打分排行，核心维度「金叉延续性」：MACD DIF/DEA 金叉后能否涨一大段、不反复横跳
- 趋势/可入手判断：金叉驱动决策树（可入手 / 过热 / 震荡 / 下跌），辅助波段适配、股息
- 扫描进度实时展示，高分股一键加入自选，AI 逐股点评 + 整组汇总

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

## 一键安装（Windows，无需 Docker / 命令行）

适合完全不懂技术的用户。界面是浏览器打开的网页，**不用装 Docker、Python、Node**。

1. 到 [Releases](https://github.com/xinyue-cres/ai-stock-lens/releases) 下载 `AI-Stock-Lens-win.zip`
2. 解压到你自己的目录（桌面、下载文件夹都行，**别放 C:\Program Files**）
3. 双击 `AI-Stock-Lens.exe`
4. 等黑色窗口出现"已启动"，浏览器会自动打开，直接就能用；**关闭黑色窗口 = 退出程序**

首次使用：
- **AI 功能**：右上角齿轮 ⚙ → 设置 · AI 模型 → 填 API Key（页面带"获取 API Key"链接）→ 保存
- **不填 key 也能用**：K 线、技术指标、选股打分都不依赖 AI；只有 AI 分析/点评需要 key

数据存在哪：`AI-Stock-Lens.exe` 旁边的 `data` 文件夹。换电脑 = 整个文件夹拷走。

### 常见问题

| 问题 | 解决 |
|---|---|
| 提示"Windows 已保护你的电脑" | 点"更多信息" → "仍要运行"。程序未买数字签名证书，属正常提示 |
| 杀毒软件报警 | PyInstaller 打包的 Python 程序常被误报，属正常；来源可信可加白名单 |
| 端口被占用 | 程序自动改用 8001/8002…，以浏览器打开的地址为准 |
| 想更新 | 下载新版本解压到新文件夹；旧的 `data` 文件夹拷过去即可保留数据 |

## 用 Docker 启动（熟悉技术的用户）

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
| 部署 | Windows 可执行版（双击即用）· Docker Compose · Nginx |

## 项目结构

```
ai-stock-lens/
├── backend/
│   ├── run.py               # Windows 可执行版入口（自动开浏览器）
│   └── app/
│       ├── ai/              # prompts/ + normalizers + analyzer + client
│       ├── api/             # FastAPI 路由 (signals, analysis, score, ...)
│       ├── datasource/      # 多源 provider + fallback router
│       ├── features/        # 选股打分引擎 + 趋势判断
│       ├── indicators/      # 技术指标引擎
│       ├── models/          # SQLModel 数据模型
│       └── services/        # 业务逻辑层
├── frontend/
│   └── src/
│       ├── api/             # HTTP 层 (一文件一领域)
│       ├── pages/
│       │   ├── StockList/   # 首页列表
│       │   ├── StockDetail/ # 详情页
│       │   └── Scoreboard/  # 选股打分页
│       └── features/        # 分析 / 对话 / 自选 / 设置
├── packaging/               # PyInstaller 打包 spec（Windows 可执行版）
├── .github/workflows/       # GitHub Actions（Windows 自动构建 + Release）
└── docker-compose.yaml
```
