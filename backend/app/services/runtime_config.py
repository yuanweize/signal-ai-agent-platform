"""
Runtime configuration helpers backed by BotConfig table.

Provides DB-driven feature toggles and AI prompt/key values,
with safe fallbacks to environment settings.
"""

from __future__ import annotations

import base64
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cryptography.fernet import Fernet

from app.config import settings
from app.models.config import BotConfig


KEY_AI_PROMPT = "ai_prompt"
KEY_AI_ENABLED = "is_ai_enabled"
KEY_MARKET_ENABLED = "is_market_enabled"
KEY_AI_API_KEY = "ai_api_key"  # legacy plain-text key (migration fallback)
KEY_AI_API_KEY_ENC = "ai_api_key_enc"
KEY_RETENTION_DAYS = "retention_days"
KEY_AD_AUTOMATION_ENABLED = "ad_automation_enabled"
KEY_AD_MIN_INTERVAL_MINUTES = "ad_min_interval_minutes"
KEY_AD_QUIET_HOUR_START = "ad_quiet_hour_start"
KEY_AD_QUIET_HOUR_END = "ad_quiet_hour_end"
KEY_AD_GROUP_BLACKLIST = "ad_group_blacklist"
KEY_BOT_NAME = "bot_name"

DEFAULT_AD_AUTOMATION_ENABLED = True
DEFAULT_AD_MIN_INTERVAL_MINUTES = 180
DEFAULT_AD_QUIET_HOUR_START = 23
DEFAULT_AD_QUIET_HOUR_END = 8


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _to_int(value: str | None, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _to_csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    items = [entry.strip() for entry in value.split(",")]
    return [entry for entry in items if entry]


def mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}{'*' * max(6, len(secret) - 8)}{secret[-4:]}"


def _get_fernet() -> Fernet:
    seed = settings.config_encryption_key or settings.jwt_secret_key
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_value(value: str) -> str:
    if not value:
        return ""
    return _get_fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_value(value: str) -> str:
    if not value:
        return ""
    return _get_fernet().decrypt(value.encode("utf-8")).decode("utf-8")


async def get_config_map(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(select(BotConfig.key, BotConfig.value))
    rows = result.all()
    return {key: value for key, value in rows}


async def get_runtime_settings(session: AsyncSession) -> dict:
    values = await get_config_map(session)

    ai_prompt = values.get(KEY_AI_PROMPT, settings.bot_system_prompt)
    is_ai_enabled = _to_bool(values.get(KEY_AI_ENABLED), settings.feature_ai_enabled)
    is_market_enabled = _to_bool(
        values.get(KEY_MARKET_ENABLED), settings.feature_market_enabled
    )
    ai_api_key_enc = values.get(KEY_AI_API_KEY_ENC, "")
    ai_api_key_plain = values.get(KEY_AI_API_KEY, "")
    ai_api_key = settings.ai_api_key
    if ai_api_key_enc:
        try:
            ai_api_key = decrypt_value(ai_api_key_enc)
        except Exception:
            ai_api_key = settings.ai_api_key
    elif ai_api_key_plain:
        ai_api_key = ai_api_key_plain

    retention_days_raw = values.get(KEY_RETENTION_DAYS)
    retention_days = _to_int(retention_days_raw, settings.data_retention_days, minimum=1)
    ad_automation_enabled = _to_bool(
        values.get(KEY_AD_AUTOMATION_ENABLED),
        DEFAULT_AD_AUTOMATION_ENABLED,
    )
    ad_min_interval_minutes = _to_int(
        values.get(KEY_AD_MIN_INTERVAL_MINUTES),
        DEFAULT_AD_MIN_INTERVAL_MINUTES,
        minimum=1,
        maximum=1440,
    )
    ad_quiet_hour_start = _to_int(
        values.get(KEY_AD_QUIET_HOUR_START),
        DEFAULT_AD_QUIET_HOUR_START,
        minimum=0,
        maximum=23,
    )
    ad_quiet_hour_end = _to_int(
        values.get(KEY_AD_QUIET_HOUR_END),
        DEFAULT_AD_QUIET_HOUR_END,
        minimum=0,
        maximum=23,
    )
    ad_group_blacklist = _to_csv_list(values.get(KEY_AD_GROUP_BLACKLIST))
    bot_name = (values.get(KEY_BOT_NAME) or settings.bot_name).strip() or settings.bot_name

    return {
        "ai_prompt": ai_prompt,
        "is_ai_enabled": is_ai_enabled,
        "is_market_enabled": is_market_enabled,
        "ai_api_key": ai_api_key,
        "ai_api_key_masked": mask_secret(ai_api_key),
        "has_ai_api_key": bool(ai_api_key),
        "retention_days": retention_days,
        "ad_automation_enabled": ad_automation_enabled,
        "ad_min_interval_minutes": ad_min_interval_minutes,
        "ad_quiet_hour_start": ad_quiet_hour_start,
        "ad_quiet_hour_end": ad_quiet_hour_end,
        "ad_group_blacklist": ad_group_blacklist,
        "bot_name": bot_name,
    }


async def get_runtime_settings_snapshot(session: AsyncSession) -> dict:
    current = await get_runtime_settings(session)
    return {
        "ai_prompt": current["ai_prompt"],
        "is_ai_enabled": current["is_ai_enabled"],
        "is_market_enabled": current["is_market_enabled"],
        "retention_days": current["retention_days"],
        "has_ai_api_key": current["has_ai_api_key"],
        "ad_automation_enabled": current["ad_automation_enabled"],
        "ad_min_interval_minutes": current["ad_min_interval_minutes"],
        "ad_quiet_hour_start": current["ad_quiet_hour_start"],
        "ad_quiet_hour_end": current["ad_quiet_hour_end"],
        "ad_group_blacklist": current["ad_group_blacklist"],
        "bot_name": current["bot_name"],
    }


async def upsert_runtime_settings(
    session: AsyncSession,
    *,
    ai_prompt: str | None = None,
    is_ai_enabled: bool | None = None,
    is_market_enabled: bool | None = None,
    ai_api_key: str | None = None,
    retention_days: int | None = None,
    ad_automation_enabled: bool | None = None,
    ad_min_interval_minutes: int | None = None,
    ad_quiet_hour_start: int | None = None,
    ad_quiet_hour_end: int | None = None,
    ad_group_blacklist: list[str] | None = None,
    bot_name: str | None = None,
) -> dict:
    config_map = await get_config_map(session)

    updates: dict[str, str] = {}
    if ai_prompt is not None:
        updates[KEY_AI_PROMPT] = ai_prompt.strip()
    if is_ai_enabled is not None:
        updates[KEY_AI_ENABLED] = "true" if is_ai_enabled else "false"
    if is_market_enabled is not None:
        updates[KEY_MARKET_ENABLED] = "true" if is_market_enabled else "false"
    if ai_api_key is not None:
        updates[KEY_AI_API_KEY_ENC] = encrypt_value(ai_api_key.strip())
    if retention_days is not None:
        updates[KEY_RETENTION_DAYS] = str(max(1, retention_days))
    if ad_automation_enabled is not None:
        updates[KEY_AD_AUTOMATION_ENABLED] = "true" if ad_automation_enabled else "false"
    if ad_min_interval_minutes is not None:
        updates[KEY_AD_MIN_INTERVAL_MINUTES] = str(max(1, min(1440, ad_min_interval_minutes)))
    if ad_quiet_hour_start is not None:
        updates[KEY_AD_QUIET_HOUR_START] = str(max(0, min(23, ad_quiet_hour_start)))
    if ad_quiet_hour_end is not None:
        updates[KEY_AD_QUIET_HOUR_END] = str(max(0, min(23, ad_quiet_hour_end)))
    if ad_group_blacklist is not None:
        normalized = [entry.strip() for entry in ad_group_blacklist if entry and entry.strip()]
        updates[KEY_AD_GROUP_BLACKLIST] = ",".join(normalized)
    if bot_name is not None:
        updates[KEY_BOT_NAME] = bot_name.strip()[:80]

    for key, value in updates.items():
        if key in config_map:
            result = await session.execute(select(BotConfig).where(BotConfig.key == key))
            row = result.scalar_one()
            row.value = value
        else:
            session.add(
                BotConfig(
                    key=key,
                    value=value,
                    category="runtime",
                    description=f"Runtime setting: {key}",
                )
            )

    if ai_api_key is not None and KEY_AI_API_KEY in config_map:
        plain_result = await session.execute(
            select(BotConfig).where(BotConfig.key == KEY_AI_API_KEY)
        )
        plain_row = plain_result.scalar_one_or_none()
        if plain_row:
            plain_row.value = ""

    await session.commit()
    return await get_runtime_settings(session)


def summarize_runtime_settings(data: dict) -> str:
    return json.dumps(
        {
            "is_ai_enabled": data.get("is_ai_enabled"),
            "is_market_enabled": data.get("is_market_enabled"),
            "retention_days": data.get("retention_days"),
            "has_ai_api_key": data.get("has_ai_api_key"),
            "ad_automation_enabled": data.get("ad_automation_enabled"),
            "ad_min_interval_minutes": data.get("ad_min_interval_minutes"),
            "ad_quiet_hour_start": data.get("ad_quiet_hour_start"),
            "ad_quiet_hour_end": data.get("ad_quiet_hour_end"),
            "ad_group_blacklist": data.get("ad_group_blacklist"),
            "bot_name": data.get("bot_name"),
        },
        ensure_ascii=False,
    )
