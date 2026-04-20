"""
Auth API — login endpoint with optional TOTP 2FA.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.api.deps import create_access_token
from app.schemas.auth import LoginRequest, TokenResponse

logger = logging.getLogger("api.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """
    Admin login — returns JWT on success.

    Validates username + password. If ADMIN_TOTP_SECRET is configured,
    also requires a valid TOTP code.
    """
    # Validate credentials
    if (
        request.username != settings.admin_username
        or request.password != settings.admin_password
    ):
        logger.warning(f"❌ Failed login attempt: {request.username}")
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
    token, expires_in = create_access_token(request.username)

    logger.info(f"✅ Admin login: {request.username}")
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
