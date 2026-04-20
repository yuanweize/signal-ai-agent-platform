"""
Auth API — login endpoint with optional TOTP 2FA.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.api.deps import create_access_token
from app.database import get_session
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.audit_log import write_audit_log
from app.services.auth_guard import login_guard
from app.services.metrics import runtime_metrics

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
    if (
        username != settings.admin_username
        or request.password != settings.admin_password
    ):
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
    if settings.is_2fa_enabled:
        if not request.totp_code:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="TOTP code required (2FA is enabled)",
            )

        try:
            import pyotp

            totp = pyotp.TOTP(settings.admin_totp_secret)
            if not totp.verify(request.totp_code, valid_window=1):
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
        except ImportError:
            logger.error("pyotp not installed but TOTP secret is configured")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server 2FA configuration error",
            )

    # Generate JWT
    token, expires_in = create_access_token(username)
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


@router.get("/me")
async def get_me():
    """Check 2FA requirement (public — no auth needed)."""
    return {
        "requires_2fa": settings.is_2fa_enabled,
    }
