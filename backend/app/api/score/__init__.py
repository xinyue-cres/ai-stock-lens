"""打分 API 包：把原 api/score.py（477行）拆为 list/detail/ai/combined 四个子路由 + 共享模型/工具。

对外公开 `router` —— app/main.py 直接 include_router(score.router)，无需改注册代码。
公开接口与原来完全一致：
- GET /list                                /api/score/list
- POST /scan, GET /scan/status, POST /scan/cancel
- GET /{code}                              /api/score/600519
- POST /trend/{code}
- POST /summarize, POST /analyze-batch
- GET /combined/list, GET /combined/{code}
"""
from fastapi import APIRouter

from . import ai, combined, detail, list

router = APIRouter(prefix="/api/score", tags=["score"])
router.include_router(list.router)
router.include_router(detail.router)
router.include_router(ai.router)
router.include_router(combined.router)
