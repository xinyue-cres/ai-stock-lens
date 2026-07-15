"""FastAPI 入口。"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import analysis, chat, compare, positions, review, settings, signals, stocks, sync, watchlist
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
app.include_router(analysis.router)
app.include_router(chat.router)
app.include_router(signals.router)
app.include_router(sync.router)
app.include_router(compare.router)
app.include_router(settings.router)
app.include_router(review.router)
app.include_router(positions.router)
