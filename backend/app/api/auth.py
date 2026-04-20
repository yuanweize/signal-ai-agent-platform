"""
Auth API — login endpoint with optional TOTP 2FA.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import create_access_token
from app.database import get_session
from app.schemas.auth import (
    AuthStatusResponse,
    BootstrapInitRequest,
    BootstrapInitResponse,
    LoginRequest,
    TokenResponse,
)
from app.services.audit_log import write_audit_log
from app.services.auth_guard import login_guard
from app.services.metrics import runtime_metrics
from app.services.security_bootstrap import (
    get_admin_username,
    get_bootstrap_status,
    initialize_bootstrap,
    verify_credentials,
    verify_totp,
)

logger = logging.getLogger("api.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(
    request: LoginRequest,
    http_request: Request,
    session: AsyncSession = Depends(get_session),
):
    """
    Admin login — returns JWT on success.

    Validates username + password. If ADMIN_TOTP_SECRET is configured,
    also requires a valid TOTP code.
    """
    ip_address = http_request.client.host if http_request.client else "unknown"
    username = request.username.strip()
    bootstrap_status = await get_bootstrap_status(session)

    if bootstrap_status.bootstrap_required:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System setup required before login",
        )

    allowed, retry_after = login_guard.check_allowed(ip_address, username)
    if not allowed:
        runtime_metrics.inc("api.requests.401")
        await write_audit_log(
            session,
            actor=username or "unknown",
            action="auth.login.blocked",
            target="admin",
            status="blocked",
            ip_address=ip_address,
            details={"retry_after_seconds": retry_after},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Retry after {retry_after}s",
        )

    # Validate credentials
    if not await verify_credentials(session, username, request.password):
        logger.warning(f"❌ Failed login attempt: {username}")
        login_guard.on_failed_attempt(ip_address, username)
        await write_audit_log(
            session,
            actor=username or "unknown",
            action="auth.login.failed",
            target="admin",
            status="failed",
            ip_address=ip_address,
            details={"reason": "invalid_credentials"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Validate TOTP if 2FA is enabled
    if not await verify_totp(session, request.totp_code):
        login_guard.on_failed_attempt(ip_address, username)
        await write_audit_log(
            session,
            actor=username,
            action="auth.login.failed",
            target="admin",
            status="failed",
            ip_address=ip_address,
            details={"reason": "invalid_totp"},
        )
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid TOTP code",
        )

    configured_username = await get_admin_username(session)
    if username.strip().lower() != configured_username:
        logger.error("Credential verification mismatch with configured username")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server authentication configuration error",
        )

    # Generate JWT
    token, expires_in = await create_access_token(configured_username, session)
    login_guard.on_success(ip_address, username)

    logger.info(f"✅ Admin login: {username}")
    await write_audit_log(
        session,
        actor=username,
        action="auth.login.success",
        target="admin",
        status="success",
        ip_address=ip_address,
    )
    await session.commit()
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
    )


@router.get("/me", response_model=AuthStatusResponse)
async def get_me(session: AsyncSession = Depends(get_session)):
    """Public auth status for login/setup UI."""
    status_info = await get_bootstrap_status(session)
    return {
        "requires_2fa": status_info.requires_2fa,
        "bootstrap_required": status_info.bootstrap_required,
    }


@router.post("/bootstrap/init", response_model=BootstrapInitResponse)
async def bootstrap_init(
    request: BootstrapInitRequest,
    session: AsyncSession = Depends(get_session),
):
    """First-run secure initialization (one-time, no auth)."""
    if request.password != request.password_confirm:
        raise HTTPException(status_code=400, detail="Passwords do not match")

    try:
        generated_secret = await initialize_bootstrap(
            session,
            username=request.username,
            password=request.password,
            totp_secret=request.totp_secret,
        )
    except ValueError as exc:
        message = str(exc)
        status_code = 409 if "already initialized" in message.lower() else 400
        raise HTTPException(status_code=status_code, detail=message)

    return BootstrapInitResponse(
        initialized=True,
        username=request.username.strip().lower() or "admin",
        generated_totp_secret=generated_secret,
    )
