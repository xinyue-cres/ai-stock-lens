"""FastAPI 入口。"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from app.api import analysis, action_plan, chat, compare, groups, market, positions, review, score, settings, signals, stocks, sync, watchlist
from app.config import get_settings
from app.db import init_db
from app.scheduler import start_scheduler, stop_scheduler

logging.basicConfig(level=get_settings().app_log_level, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    start_scheduler()
    logger.info("应用启动完成")
    yield
    stop_scheduler()
    logger.info("应用已停止")


app = FastAPI(title="AI Stock Lens", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "0.1.0"}


app.include_router(stocks.router)
app.include_router(watchlist.router)
app.include_router(groups.router)
app.include_router(analysis.router)
app.include_router(action_plan.router)
app.include_router(compare.router)
app.include_router(market.router)
app.include_router(chat.router)
app.include_router(signals.router)
app.include_router(sync.router)
app.include_router(settings.router)
app.include_router(review.router)
app.include_router(positions.router)
app.include_router(score.router)


def _static_dir() -> str | None:
    """前端构建产物目录；不存在返回 None（纯 API 模式，不影响 Docker/dev 流程）。

    - 打包态（PyInstaller）：frontend/dist 作为 data 打进 _MEIPASS 资源目录
    - 源码态：仓库 frontend/dist（需先 pnpm build）
    """
    if getattr(sys, "frozen", False):
        return os.path.join(sys._MEIPASS, "frontend_dist")  # type: ignore[attr-defined]
    dev = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist"))
    return dev if os.path.isdir(dev) else None


# 静态托管前端 + SPA fallback（BrowserRouter 深链如 /stock/600519 回退 index.html）
_static = _static_dir()
if _static and os.path.isdir(_static):
    @app.get("/{full_path:path}", response_model=None)
    def spa(full_path: str):
        # API 未匹配的路径不落入 SPA，保持 JSON 404
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        file = os.path.join(_static, full_path)
        if os.path.isfile(file):
            return FileResponse(file)
        return FileResponse(os.path.join(_static, "index.html"))
