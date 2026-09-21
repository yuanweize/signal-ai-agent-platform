"""
Runtime configuration helpers backed by BotConfig table.

Provides DB-driven feature toggles and AI prompt/key values.
"""

from __future__ import annotations

import base64
import hashlib
import ipaddress
import json
from datetime import UTC, datetime
from urllib.parse import urlparse

from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.config import BotConfig

KEY_AI_PROMPT = "ai_prompt"
KEY_AI_ENABLED = "is_ai_enabled"
KEY_MARKET_ENABLED = "is_market_enabled"
KEY_AI_API_KEY = "ai_api_key"  # legacy plain-text key (migration fallback)
KEY_AI_API_KEY_ENC = "ai_api_key_enc"
KEY_AI_API_BASE_URL = "ai_api_base_url"
KEY_AI_MODEL = "ai_model"
KEY_AI_TEMPERATURE = "ai_temperature"
KEY_AI_MAX_TOKENS = "ai_max_tokens"
KEY_AI_CONTEXT_MESSAGES = "ai_context_messages"
KEY_AI_MODELS_CACHE = "ai_models_cache_json"
KEY_RETENTION_DAYS = "retention_days"
KEY_AD_AUTOMATION_ENABLED = "ad_automation_enabled"
KEY_AD_MIN_INTERVAL_MINUTES = "ad_min_interval_minutes"
KEY_AD_QUIET_HOUR_START = "ad_quiet_hour_start"
KEY_AD_QUIET_HOUR_END = "ad_quiet_hour_end"
KEY_AD_GROUP_BLACKLIST = "ad_group_blacklist"
KEY_BOT_NAME = "bot_name"
KEY_SIGNAL_API_URL = "signal_api_url"
KEY_SIGNAL_API_TOKEN = "signal_api_token"  # legacy plain-text key (migration fallback)
KEY_SIGNAL_API_TOKEN_ENC = "signal_api_token_enc"
KEY_SIGNAL_PHONE_NUMBER = "signal_phone_number"
KEY_BOT_DEFAULT_LANGUAGE = "bot_default_language"

DEFAULT_AI_PROMPT = "You are a helpful sales assistant. Reply naturally and professionally."
DEFAULT_AI_ENABLED = False
DEFAULT_MARKET_ENABLED = True
DEFAULT_AI_API_BASE_URL = ""
DEFAULT_AI_MODEL = ""
DEFAULT_AI_TEMPERATURE = 0.7
DEFAULT_AI_MAX_TOKENS = 1000
DEFAULT_AI_CONTEXT_MESSAGES = 20
DEFAULT_RETENTION_DAYS = 30
DEFAULT_BOT_NAME = "Signal Market Bot"

DEFAULT_AD_AUTOMATION_ENABLED = True
DEFAULT_AD_MIN_INTERVAL_MINUTES = 180
DEFAULT_AD_QUIET_HOUR_START = 23
DEFAULT_AD_QUIET_HOUR_END = 8
DEFAULT_SIGNAL_API_URL = ""
DEFAULT_SIGNAL_PHONE_NUMBER = ""
DEFAULT_BOT_DEFAULT_LANGUAGE = "cs"


def _to_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _to_int(
    value: str | None, default: int, minimum: int | None = None, maximum: int | None = None
) -> int:
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


def _to_float(
    value: str | None, default: float, minimum: float | None = None, maximum: float | None = None
) -> float:
    if value is None:
        return default
    try:
        parsed = float(value)
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


def _parse_models_cache(raw: str | None) -> tuple[list[str], list[str], int, str | None]:
    if not raw:
        return [], [], 0, None
    try:
        data = json.loads(raw)
    except Exception:
        return [], [], 0, None
    models = data.get("valid_models")
    if models is None:
        models = data.get("models")
    if not isinstance(models, list):
        models = []
    invalid_models_raw = data.get("invalid_models")
    invalid_models: list[str] = []
    if isinstance(invalid_models_raw, list):
        for item in invalid_models_raw:
            if isinstance(item, dict):
                model_id = str(item.get("model") or "").strip()
            else:
                model_id = str(item).strip()
            if model_id:
                invalid_models.append(model_id)
    listed_total = data.get("listed_total")
    if not isinstance(listed_total, int) or listed_total < 0:
        listed_total = len(models) + len(invalid_models)
    normalized_models = [str(item).strip() for item in models if str(item).strip()]
    updated_at = data.get("updated_at")
    normalized_invalid = [str(item).strip() for item in invalid_models if str(item).strip()]
    return (
        sorted(set(normalized_models), key=lambda v: v.lower())[:500],
        sorted(set(normalized_invalid), key=lambda v: v.lower())[:500],
        listed_total,
        (str(updated_at) if updated_at else None),
    )


def detect_ai_provider(base_url: str) -> str:
    try:
        host = (urlparse(base_url).hostname or "").lower()
    except Exception:
        return "unknown"

    if not host:
        return "unknown"
    if "openrouter" in host:
        return "openrouter"
    try:
        ip = ipaddress.ip_address(host)
        if ip in ipaddress.ip_network("100.64.0.0/10"):
            return "tailscale-ai-gateway"
    except ValueError:
        pass
    if "openai.azure" in host or host.endswith(".azure.com"):
        return "azure-openai-compatible"
    if "api.openai.com" in host:
        return "openai"
    if "gateway.ai" in host or "tailscale" in host:
        return "tailscale-ai-gateway"
    if host in {"localhost", "127.0.0.1"}:
        return "local-openai-compatible"
    return "openai-compatible"


def is_ai_api_key_optional(base_url: str) -> bool:
    provider = detect_ai_provider(base_url)
    return provider in {"tailscale-ai-gateway", "local-openai-compatible"}


def mask_secret(secret: str) -> str:
    if not secret:
        return ""
    if len(secret) <= 8:
        return "*" * len(secret)
    return f"{secret[:4]}{'*' * max(6, len(secret) - 8)}{secret[-4:]}"


def _get_fernet() -> Fernet:
    seed = settings.config_encryption_key or settings.jwt_secret_key or "runtime-config-fallback"
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

    ai_prompt = values.get(KEY_AI_PROMPT, DEFAULT_AI_PROMPT)
    is_ai_enabled = _to_bool(values.get(KEY_AI_ENABLED), DEFAULT_AI_ENABLED)
    is_market_enabled = _to_bool(values.get(KEY_MARKET_ENABLED), DEFAULT_MARKET_ENABLED)
    ai_api_key_enc = values.get(KEY_AI_API_KEY_ENC, "")
    ai_api_key_plain = values.get(KEY_AI_API_KEY, "")
    ai_api_key = ""
    ai_api_key_source = "none"
    if ai_api_key_enc:
        try:
            ai_api_key = decrypt_value(ai_api_key_enc)
            ai_api_key_source = "runtime"
        except Exception:
            ai_api_key = ""
            ai_api_key_source = "invalid"
    elif ai_api_key_plain:
        ai_api_key = ai_api_key_plain
        ai_api_key_source = "runtime"

    ai_api_base_url_raw = (values.get(KEY_AI_API_BASE_URL) or "").strip()
    ai_api_base_url = ai_api_base_url_raw or DEFAULT_AI_API_BASE_URL
    ai_model_raw = (values.get(KEY_AI_MODEL) or "").strip()
    ai_model = ai_model_raw or DEFAULT_AI_MODEL
    ai_provider_detected = detect_ai_provider(ai_api_base_url)
    ai_temperature = _to_float(
        values.get(KEY_AI_TEMPERATURE),
        DEFAULT_AI_TEMPERATURE,
        minimum=0.0,
        maximum=2.0,
    )
    ai_max_tokens = _to_int(
        values.get(KEY_AI_MAX_TOKENS),
        DEFAULT_AI_MAX_TOKENS,
        minimum=1,
        maximum=32000,
    )
    ai_context_messages = _to_int(
        values.get(KEY_AI_CONTEXT_MESSAGES),
        DEFAULT_AI_CONTEXT_MESSAGES,
        minimum=1,
        maximum=200,
    )
    ai_models_cached, ai_models_invalid, ai_models_listed_total, ai_models_cached_at = (
        _parse_models_cache(values.get(KEY_AI_MODELS_CACHE))
    )

    retention_days_raw = values.get(KEY_RETENTION_DAYS)
    retention_days = _to_int(retention_days_raw, DEFAULT_RETENTION_DAYS, minimum=1)
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
    bot_name = (values.get(KEY_BOT_NAME) or DEFAULT_BOT_NAME).strip() or DEFAULT_BOT_NAME
    signal_api_url = (
        values.get(KEY_SIGNAL_API_URL) or settings.signal_api_url or DEFAULT_SIGNAL_API_URL
    ).strip()
    signal_phone_number = (
        values.get(KEY_SIGNAL_PHONE_NUMBER)
        or settings.signal_phone_number
        or DEFAULT_SIGNAL_PHONE_NUMBER
    ).strip()
    bot_default_language = (
        values.get(KEY_BOT_DEFAULT_LANGUAGE)
        or settings.bot_default_language
        or DEFAULT_BOT_DEFAULT_LANGUAGE
    ).strip() or DEFAULT_BOT_DEFAULT_LANGUAGE

    signal_api_token_enc = values.get(KEY_SIGNAL_API_TOKEN_ENC, "")
    signal_api_token_plain = values.get(KEY_SIGNAL_API_TOKEN, "")
    signal_api_token = ""
    signal_api_token_source = "none"
    if signal_api_token_enc:
        try:
            signal_api_token = decrypt_value(signal_api_token_enc)
            signal_api_token_source = "runtime"
        except Exception:
            signal_api_token = ""
            signal_api_token_source = "invalid"
    elif signal_api_token_plain:
        signal_api_token = signal_api_token_plain
        signal_api_token_source = "runtime"

    return {
        "ai_prompt": ai_prompt,
        "is_ai_enabled": is_ai_enabled,
        "is_market_enabled": is_market_enabled,
        "ai_api_key": ai_api_key,
        "ai_api_key_masked": mask_secret(ai_api_key),
        "has_ai_api_key": bool(ai_api_key),
        "ai_api_key_source": ai_api_key_source,
        "ai_api_base_url": ai_api_base_url,
        "ai_provider_detected": ai_provider_detected,
        "ai_model": ai_model,
        "ai_temperature": ai_temperature,
        "ai_max_tokens": ai_max_tokens,
        "ai_context_messages": ai_context_messages,
        "ai_models_cached": ai_models_cached,
        "ai_models_cached_invalid": ai_models_invalid,
        "ai_models_listed_total": ai_models_listed_total,
        "ai_models_cached_at": ai_models_cached_at,
        "retention_days": retention_days,
        "ad_automation_enabled": ad_automation_enabled,
        "ad_min_interval_minutes": ad_min_interval_minutes,
        "ad_quiet_hour_start": ad_quiet_hour_start,
        "ad_quiet_hour_end": ad_quiet_hour_end,
        "ad_group_blacklist": ad_group_blacklist,
        "bot_name": bot_name,
        "signal_api_url": signal_api_url,
        "signal_phone_number": signal_phone_number,
        "signal_api_token": signal_api_token,
        "signal_api_token_masked": mask_secret(signal_api_token),
        "has_signal_api_token": bool(signal_api_token),
        "signal_api_token_source": signal_api_token_source,
        "bot_default_language": bot_default_language,
    }


async def get_runtime_settings_snapshot(session: AsyncSession) -> dict:
    current = await get_runtime_settings(session)
    return {
        "ai_prompt": current["ai_prompt"],
        "is_ai_enabled": current["is_ai_enabled"],
        "is_market_enabled": current["is_market_enabled"],
        "ai_api_base_url": current["ai_api_base_url"],
        "ai_provider_detected": current["ai_provider_detected"],
        "ai_model": current["ai_model"],
        "ai_temperature": current["ai_temperature"],
        "ai_max_tokens": current["ai_max_tokens"],
        "ai_context_messages": current["ai_context_messages"],
        "retention_days": current["retention_days"],
        "has_ai_api_key": current["has_ai_api_key"],
        "ai_api_key_source": current["ai_api_key_source"],
        "ad_automation_enabled": current["ad_automation_enabled"],
        "ad_min_interval_minutes": current["ad_min_interval_minutes"],
        "ad_quiet_hour_start": current["ad_quiet_hour_start"],
        "ad_quiet_hour_end": current["ad_quiet_hour_end"],
        "ad_group_blacklist": current["ad_group_blacklist"],
        "bot_name": current["bot_name"],
        "signal_api_url": current["signal_api_url"],
        "signal_phone_number": current["signal_phone_number"],
        "has_signal_api_token": current["has_signal_api_token"],
        "signal_api_token_source": current["signal_api_token_source"],
        "bot_default_language": current["bot_default_language"],
    }


async def upsert_runtime_settings(
    session: AsyncSession,
    *,
    ai_prompt: str | None = None,
    is_ai_enabled: bool | None = None,
    is_market_enabled: bool | None = None,
    ai_api_key: str | None = None,
    ai_api_base_url: str | None = None,
    ai_model: str | None = None,
    ai_temperature: float | None = None,
    ai_max_tokens: int | None = None,
    ai_context_messages: int | None = None,
    retention_days: int | None = None,
    ad_automation_enabled: bool | None = None,
    ad_min_interval_minutes: int | None = None,
    ad_quiet_hour_start: int | None = None,
    ad_quiet_hour_end: int | None = None,
    ad_group_blacklist: list[str] | None = None,
    bot_name: str | None = None,
    signal_api_url: str | None = None,
    signal_api_token: str | None = None,
    signal_phone_number: str | None = None,
    bot_default_language: str | None = None,
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
    if ai_api_base_url is not None:
        updates[KEY_AI_API_BASE_URL] = ai_api_base_url.strip()
    if ai_model is not None:
        updates[KEY_AI_MODEL] = ai_model.strip()
    if ai_temperature is not None:
        updates[KEY_AI_TEMPERATURE] = str(max(0.0, min(2.0, ai_temperature)))
    if ai_max_tokens is not None:
        updates[KEY_AI_MAX_TOKENS] = str(max(1, min(32000, ai_max_tokens)))
    if ai_context_messages is not None:
        updates[KEY_AI_CONTEXT_MESSAGES] = str(max(1, min(200, ai_context_messages)))
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
    if signal_api_url is not None:
        updates[KEY_SIGNAL_API_URL] = signal_api_url.strip()
    if signal_api_token is not None:
        updates[KEY_SIGNAL_API_TOKEN_ENC] = encrypt_value(signal_api_token.strip())
    if signal_phone_number is not None:
        updates[KEY_SIGNAL_PHONE_NUMBER] = signal_phone_number.strip()
    if bot_default_language is not None:
        updates[KEY_BOT_DEFAULT_LANGUAGE] = bot_default_language.strip()[:12]

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

    if signal_api_token is not None and KEY_SIGNAL_API_TOKEN in config_map:
        signal_plain_result = await session.execute(
            select(BotConfig).where(BotConfig.key == KEY_SIGNAL_API_TOKEN)
        )
        signal_plain_row = signal_plain_result.scalar_one_or_none()
        if signal_plain_row:
            signal_plain_row.value = ""

    await session.commit()
    return await get_runtime_settings(session)


async def cache_ai_probe_models(
    session: AsyncSession,
    *,
    listed_models: list[str],
    valid_models: list[str],
    invalid_models: list[dict],
    listed_total: int,
    verified_total: int,
    provider_detected: str,
    requested_base_url: str,
    effective_base_url: str | None,
    message: str,
    probe_ok: bool,
) -> None:
    config_map = await get_config_map(session)
    normalized_listed = sorted(
        {m.strip() for m in listed_models if m and m.strip()}, key=lambda v: v.lower()
    )[:500]
    normalized_valid = sorted(
        {m.strip() for m in valid_models if m and m.strip()}, key=lambda v: v.lower()
    )[:500]
    normalized_invalid = []
    for item in invalid_models[:1000]:
        model_id = str(item.get("model") or "").strip()
        if not model_id:
            continue
        normalized_invalid.append(
            {
                "model": model_id,
                "reason": str(item.get("reason") or "unavailable")[:200],
            }
        )

    payload = {
        "listed_models": normalized_listed,
        "valid_models": normalized_valid,
        "invalid_models": normalized_invalid,
        "listed_total": max(0, int(listed_total)),
        "verified_total": max(0, int(verified_total)),
        "valid_total": len(normalized_valid),
        "invalid_total": len(normalized_invalid),
        "provider_detected": provider_detected,
        "requested_base_url": requested_base_url,
        "effective_base_url": effective_base_url,
        "message": message,
        "probe_ok": probe_ok,
        "updated_at": datetime.now(UTC).isoformat(),
    }
    value = json.dumps(payload, ensure_ascii=False)

    if KEY_AI_MODELS_CACHE in config_map:
        result = await session.execute(
            select(BotConfig).where(BotConfig.key == KEY_AI_MODELS_CACHE)
        )
        row = result.scalar_one()
        row.value = value
    else:
        session.add(
            BotConfig(
                key=KEY_AI_MODELS_CACHE,
                value=value,
                category="runtime",
                description="Runtime setting: cached AI probe model list",
            )
        )
    await session.commit()


def summarize_runtime_settings(data: dict) -> str:
    return json.dumps(
        {
            "is_ai_enabled": data.get("is_ai_enabled"),
            "is_market_enabled": data.get("is_market_enabled"),
            "ai_api_base_url": data.get("ai_api_base_url"),
            "ai_provider_detected": data.get("ai_provider_detected"),
            "ai_model": data.get("ai_model"),
            "ai_temperature": data.get("ai_temperature"),
            "ai_max_tokens": data.get("ai_max_tokens"),
            "ai_context_messages": data.get("ai_context_messages"),
            "retention_days": data.get("retention_days"),
            "has_ai_api_key": data.get("has_ai_api_key"),
            "ai_api_key_source": data.get("ai_api_key_source"),
            "ad_automation_enabled": data.get("ad_automation_enabled"),
            "ad_min_interval_minutes": data.get("ad_min_interval_minutes"),
            "ad_quiet_hour_start": data.get("ad_quiet_hour_start"),
            "ad_quiet_hour_end": data.get("ad_quiet_hour_end"),
            "ad_group_blacklist": data.get("ad_group_blacklist"),
            "bot_name": data.get("bot_name"),
            "signal_api_url": data.get("signal_api_url"),
            "signal_phone_number": data.get("signal_phone_number"),
            "has_signal_api_token": data.get("has_signal_api_token"),
            "signal_api_token_source": data.get("signal_api_token_source"),
            "bot_default_language": data.get("bot_default_language"),
        },
        ensure_ascii=False,
    )
