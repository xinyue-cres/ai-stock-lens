# AI Stock Lens

个人自用的 A 股技术分析工作台：AI 多视角分析 + MACD 金叉打分 + 统一操作指示，本地部署。

## 它做什么

**AI 分析**
牛熊辩论 / 反量化 / 反身性三视角并行喂给 Trader Agent，输出带价位/仓位/止损的操作清单；个股对话带全上下文流式输出。

**选股打分**（无需 AI key）
MACD 金叉延续性打分。**日线 / 周线 / 综合** 三视图切换：周看方向、日定时机，综合页按 7 档合并（strong_buy → avoid），详情页给"当前已涨 / 剩余预期"三维空间。趋势状态机 8 态 + 过峰置信度 0-100 分级。

**自选管理**
多对多分组 + 批量加入/移出 + 乐观刷新。全 A 元数据 7569 条已内置，添加股票秒级联想。

## 一键安装（Windows，无需 Docker / 命令行）

1. 到 [Releases](https://github.com/xinyue-cres/ai-stock-lens/releases) 下载 zip 解压
2. 双击 `AI-Stock-Lens.exe`，浏览器自动打开即用；关黑窗 = 退出

首次启动从内置种子初始化数据，首搜即秒出。填 ⚙ AI Key 才用 AI 分析；不填也能用 K 线、指标、打分。

## 开发

```bash
cp backend/.env.example backend/.env && docker compose up -d        # Docker

cd backend && source .venv/bin/activate && uvicorn app.main:app --port 8000   # 后端
cd frontend && pnpm install && pnpm dev                                        # 前端
```

技术栈：Python 3.12 / FastAPI / SQLModel / SQLite / AKShare / DeepSeek / React 18 / Vite / TS / Ant Design。
结构见 [DESIGN.md](./DESIGN.md)。
