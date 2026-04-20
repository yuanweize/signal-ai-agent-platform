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


class AuthStatusResponse(BaseModel):
    """Public auth status for login/setup page."""

    requires_2fa: bool
    bootstrap_required: bool


class BootstrapInitRequest(BaseModel):
    """First-run bootstrap payload."""

    username: str = "admin"
    password: str
    password_confirm: str
    totp_secret: str | None = None


class BootstrapInitResponse(BaseModel):
    """Bootstrap result shown once to the operator."""

    initialized: bool
    username: str
    generated_totp_secret: str | None = None
