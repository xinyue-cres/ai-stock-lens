# AI Stock Lens

本地部署、局域网访问的 A 股技术分析工具。仅分析交易数据（K 线、均线、量能、技术指标、资金流、相对强弱），不涉及基本面。AI 生成技术面分析报告与操作倾向。

方案设计详见 [DESIGN.md](./DESIGN.md)。

## 快速开始

```bash
# 1. 配置环境变量
cp backend/.env.example backend/.env
# 编辑 backend/.env，填入 DeepSeek/通义/智谱 的 AI_API_KEY

# 2. 启动
docker compose up -d

# 3. 访问
open http://localhost:8080
```

局域网内其他设备访问：`http://<主机内网 IP>:8080`

## 项目结构

```
ai-stock-lens/
├── DESIGN.md              # 方案设计文档
├── docker-compose.yaml    # 一键启动
├── backend/               # FastAPI + Python
└── frontend/              # React + Vite + lightweight-charts
```

## 技术栈

- 后端：Python 3.11 + FastAPI + SQLModel + SQLite
- 数据源：AKShare（主，预留 efinance/Tushare/BaoStock）
- 指标：pandas-ta
- AI：OpenAI 兼容协议（默认 DeepSeek）
- 前端：React 18 + Vite + TypeScript + Ant Design + TradingView lightweight-charts
