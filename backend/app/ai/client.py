"""OpenAI 兼容协议客户端。运行时从 settings_service 拿配置。"""
from __future__ import annotations

from openai import OpenAI

from app.services.settings_service import get_ai_config


def get_ai_client() -> OpenAI:
    cfg = get_ai_config()
    return OpenAI(api_key=cfg.get("api_key", ""), base_url=cfg.get("base_url"))


def get_model_name() -> str:
    return get_ai_config().get("model", "")
