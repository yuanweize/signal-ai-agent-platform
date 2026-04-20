"""
Auth schemas — login request/response and JWT token models.
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    """Admin login credentials."""

    username: str
    password: str
    totp_code: str | None = None  # Optional — only when 2FA is enabled


class TokenResponse(BaseModel):
    """JWT token returned on successful login."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class AdminUser(BaseModel):
    """Authenticated admin info (decoded from JWT)."""

    username: str
