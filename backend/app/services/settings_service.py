"""应用设置服务：AI 配置（provider / base_url / model / api_key）。

优先级：DB 中的值 > .env 默认值。
UI 修改后写 DB，运行时以 DB 为准。
"""
from __future__ import annotations

import json
import logging
from typing import Any

from sqlmodel import Session, select

from app.config import get_settings
from app.db import engine
from app.models.setting import AppSetting

logger = logging.getLogger(__name__)

# 内存缓存，写 DB 时同步失效
_cache: dict[str, Any] | None = None

KEY_AI_CONFIG = "ai_config"
KEY_TOTAL_CAPITAL = "total_capital"


def _fallback_from_env() -> dict[str, Any]:
    s = get_settings()
    return {
        "provider": s.ai_provider,
        "base_url": s.ai_base_url,
        "model": s.ai_model,
        "api_key": s.ai_api_key,
    }


def _load_from_db(session: Session) -> dict[str, Any] | None:
    row = session.exec(select(AppSetting).where(AppSetting.key == KEY_AI_CONFIG)).first()
    if not row:
        return None
    try:
        return json.loads(row.value)
    except json.JSONDecodeError:
        logger.warning("ai_config 存储值不是合法 JSON，回退到 env")
        return None


def get_ai_config(force_reload: bool = False) -> dict[str, Any]:
    """当前生效的 AI 配置。DB 有则用 DB，否则回退 .env。"""
    global _cache
    if _cache is not None and not force_reload:
        return _cache

    with Session(engine) as session:
        db_val = _load_from_db(session)
    merged = _fallback_from_env()
    if db_val:
        merged.update({k: v for k, v in db_val.items() if v})
    _cache = merged
    return _cache


def save_ai_config(cfg: dict[str, Any]) -> dict[str, Any]:
    """保存 AI 配置到 DB。空字符串字段忽略（保留原值）。"""
    global _cache
    cleaned = {k: v for k, v in cfg.items() if k in {"provider", "base_url", "model", "api_key"} and v is not None}

    with Session(engine) as session:
        existing = session.exec(select(AppSetting).where(AppSetting.key == KEY_AI_CONFIG)).first()
        current = json.loads(existing.value) if existing else {}
        current.update(cleaned)
        value = json.dumps(current, ensure_ascii=False)
        if existing:
            existing.value = value
            session.add(existing)
        else:
            session.add(AppSetting(key=KEY_AI_CONFIG, value=value))
        session.commit()

    _cache = None
    return get_ai_config()


def public_ai_config() -> dict[str, Any]:
    """给前端展示的版本：api_key 打码。"""
    cfg = get_ai_config()
    key = cfg.get("api_key") or ""
    masked = key[:4] + "…" + key[-4:] if len(key) >= 10 else ("****" if key else "")
    return {
        "provider": cfg.get("provider"),
        "base_url": cfg.get("base_url"),
        "model": cfg.get("model"),
        "api_key_masked": masked,
        "has_api_key": bool(key),
    }


def get_total_capital() -> float | None:
    """获取用户设置的总资金（元）。未设置返回 None。"""
    with Session(engine) as session:
        row = session.exec(select(AppSetting).where(AppSetting.key == KEY_TOTAL_CAPITAL)).first()
    if not row:
        return None
    try:
        v = float(row.value)
        return v if v > 0 else None
    except (ValueError, TypeError):
        return None


def save_total_capital(amount: float) -> float:
    """保存总资金。"""
    with Session(engine) as session:
        existing = session.exec(select(AppSetting).where(AppSetting.key == KEY_TOTAL_CAPITAL)).first()
        if existing:
            existing.value = str(amount)
            session.add(existing)
        else:
            session.add(AppSetting(key=KEY_TOTAL_CAPITAL, value=str(amount)))
        session.commit()
    return amount
