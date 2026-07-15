from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel

from app.services import settings_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings", tags=["settings"])


# 常见 provider 预设，供前端下拉选择
PROVIDER_PRESETS = [
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "default_model": "deepseek-chat",
        "docs_url": "https://platform.deepseek.com/api_keys",
    },
    {
        "id": "qwen",
        "name": "通义千问",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "default_model": "qwen-plus",
        "docs_url": "https://bailian.console.aliyun.com/",
    },
    {
        "id": "zhipu",
        "name": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "default_model": "glm-4-flash",
        "docs_url": "https://open.bigmodel.cn/usercenter/apikeys",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "docs_url": "https://platform.openai.com/api-keys",
    },
    {
        "id": "custom",
        "name": "自定义（OpenAI 兼容）",
        "base_url": "",
        "default_model": "",
        "docs_url": "",
    },
]


class AiConfigPayload(BaseModel):
    provider: str | None = None
    base_url: str | None = None
    model: str | None = None
    api_key: str | None = None


class AiTestPayload(BaseModel):
    provider: str | None = None
    base_url: str
    model: str
    api_key: str


@router.get("/presets")
def get_presets():
    return PROVIDER_PRESETS


@router.get("/ai")
def get_ai():
    return settings_service.public_ai_config()


@router.put("/ai")
def put_ai(payload: AiConfigPayload):
    settings_service.save_ai_config(payload.model_dump(exclude_none=True))
    return settings_service.public_ai_config()


@router.post("/ai/test")
def test_ai(payload: AiTestPayload):
    """用给定的 key/url/model 打一次极简 chat，验证连通性。"""
    if not payload.api_key or not payload.base_url or not payload.model:
        raise HTTPException(status_code=400, detail="base_url / model / api_key 必填")

    try:
        client = OpenAI(api_key=payload.api_key, base_url=payload.base_url)
        resp = client.chat.completions.create(
            model=payload.model,
            messages=[
                {"role": "system", "content": "你是一个测试机器人，简短回应"},
                {"role": "user", "content": "回一句 pong"},
            ],
            max_tokens=16,
            temperature=0,
        )
        content = resp.choices[0].message.content or ""
        return {
            "ok": True,
            "model": resp.model,
            "reply": content.strip()[:120],
        }
    except Exception as e:  # noqa: BLE001
        logger.warning("AI 连通性测试失败: %s", e)
        return {"ok": False, "error": str(e)[:200]}


# -------------------- 总资金 --------------------

class CapitalPayload(BaseModel):
    amount: float


@router.get("/capital")
def get_capital():
    val = settings_service.get_total_capital()
    return {"total_capital": val}


@router.put("/capital")
def put_capital(payload: CapitalPayload):
    if payload.amount <= 0:
        raise HTTPException(400, "总资金必须大于 0")
    settings_service.save_total_capital(payload.amount)
    return {"total_capital": payload.amount}
