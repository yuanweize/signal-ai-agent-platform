"""First-run security bootstrap and admin credential helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

import pyotp
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.config import BotConfig

KEY_BOOTSTRAP_COMPLETED = "auth_bootstrap_completed"
KEY_ADMIN_USERNAME = "admin_username"
KEY_ADMIN_PASSWORD_HASH = "admin_password_hash"
KEY_ADMIN_TOTP_SECRET = "admin_totp_secret"
KEY_JWT_SIGNING_SECRET = "jwt_signing_secret"

DEFAULT_ADMIN_USERNAME = "admin"


@dataclass
class BootstrapStatus:
    bootstrap_required: bool
    requires_2fa: bool


def _normalize_username(username: str) -> str:
    return (username or "").strip().lower()


def _validate_username(username: str) -> None:
    if not re.fullmatch(r"[a-zA-Z0-9._-]{3,32}", username):
        raise ValueError("Username must be 3-32 chars and contain only letters, numbers, ., _, -")


def _validate_password(password: str) -> None:
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    if not re.search(r"[A-Z]", password):
        raise ValueError("Password must include an uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValueError("Password must include a lowercase letter")
    if not re.search(r"\d", password):
        raise ValueError("Password must include a number")
    if not re.search(r"[^A-Za-z0-9]", password):
        raise ValueError("Password must include a special character")


def _normalize_totp_secret(secret: str) -> str:
    return (secret or "").strip().replace(" ", "").upper()


def _validate_totp_secret(secret: str) -> None:
    if not re.fullmatch(r"[A-Z2-7]{16,128}", secret):
        raise ValueError("TOTP secret must be base32 format (A-Z, 2-7), at least 16 chars")
    try:
        pyotp.TOTP(secret).now()
    except Exception as exc:
        raise ValueError("Invalid TOTP secret") from exc


def _hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return (
        f"scrypt$16384$8$1$"
        f"{base64.urlsafe_b64encode(salt).decode('ascii')}"
        f"${base64.urlsafe_b64encode(digest).decode('ascii')}"
    )


def _verify_password(password: str, encoded: str) -> bool:
    try:
        prefix, n_raw, r_raw, p_raw, salt_b64, digest_b64 = encoded.split("$", 5)
        if prefix != "scrypt":
            return False
        n = int(n_raw)
        r = int(r_raw)
        p = int(p_raw)
        salt = base64.urlsafe_b64decode(salt_b64.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_b64.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False


async def get_security_config_map(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(
        select(BotConfig.key, BotConfig.value).where(
            BotConfig.key.in_(
                [
                    KEY_BOOTSTRAP_COMPLETED,
                    KEY_ADMIN_USERNAME,
                    KEY_ADMIN_PASSWORD_HASH,
                    KEY_ADMIN_TOTP_SECRET,
                    KEY_JWT_SIGNING_SECRET,
                ]
            )
        )
    )
    return {key: value for key, value in result.all()}


async def get_bootstrap_status(session: AsyncSession) -> BootstrapStatus:
    values = await get_security_config_map(session)
    completed = values.get(KEY_BOOTSTRAP_COMPLETED, "").strip().lower() == "true"
    has_hash = bool((values.get(KEY_ADMIN_PASSWORD_HASH) or "").strip())
    has_secret = bool((values.get(KEY_JWT_SIGNING_SECRET) or "").strip())
    bootstrap_required = not (completed and has_hash and has_secret)
    requires_2fa = bool((values.get(KEY_ADMIN_TOTP_SECRET) or "").strip())
    return BootstrapStatus(bootstrap_required=bootstrap_required, requires_2fa=requires_2fa)


async def initialize_bootstrap(
    session: AsyncSession,
    *,
    username: str,
    password: str,
    totp_secret: str | None,
) -> str:
    status = await get_bootstrap_status(session)
    if not status.bootstrap_required:
        raise ValueError("System is already initialized")

    normalized_username = _normalize_username(username or DEFAULT_ADMIN_USERNAME)
    normalized_totp = _normalize_totp_secret(totp_secret or "")

    _validate_username(normalized_username)
    _validate_password(password)
    if not normalized_totp:
        normalized_totp = pyotp.random_base32()
    _validate_totp_secret(normalized_totp)

    updates = {
        KEY_BOOTSTRAP_COMPLETED: "true",
        KEY_ADMIN_USERNAME: normalized_username,
        KEY_ADMIN_PASSWORD_HASH: _hash_password(password),
        KEY_ADMIN_TOTP_SECRET: normalized_totp,
        KEY_JWT_SIGNING_SECRET: secrets.token_urlsafe(64),
    }

    existing = await get_security_config_map(session)
    for key, value in updates.items():
        if key in existing:
            row = (
                await session.execute(select(BotConfig).where(BotConfig.key == key))
            ).scalar_one()
            row.value = value
            row.category = "security"
            row.description = f"Security config: {key}"
        else:
            session.add(
                BotConfig(
                    key=key,
                    value=value,
                    category="security",
                    description=f"Security config: {key}",
                )
            )

    await session.commit()
    return normalized_totp


async def get_admin_username(session: AsyncSession) -> str:
    values = await get_security_config_map(session)
    username = (values.get(KEY_ADMIN_USERNAME) or "").strip().lower()
    return username or DEFAULT_ADMIN_USERNAME


async def get_jwt_signing_secret(session: AsyncSession) -> str:
    values = await get_security_config_map(session)
    secret = (values.get(KEY_JWT_SIGNING_SECRET) or "").strip()
    return secret or "temporary-bootstrap-secret"


async def verify_credentials(session: AsyncSession, username: str, password: str) -> bool:
    values = await get_security_config_map(session)
    configured_username = await get_admin_username(session)
    if _normalize_username(username) != configured_username:
        return False

    password_hash = (values.get(KEY_ADMIN_PASSWORD_HASH) or "").strip()
    if not password_hash:
        return False

    try:
        return _verify_password(password, password_hash)
    except Exception:
        return False


async def verify_totp(session: AsyncSession, totp_code: str | None) -> bool:
    values = await get_security_config_map(session)
    secret = (values.get(KEY_ADMIN_TOTP_SECRET) or "").strip()
    if not secret:
        return True

    if not totp_code:
        return False

    try:
        totp = pyotp.TOTP(secret)
        return bool(totp.verify(totp_code, valid_window=1))
    except Exception:
        return False
