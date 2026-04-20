"""
Shared API dependencies — authentication and database session.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from jose import jwt, JWTError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings
from app.schemas.auth import AdminUser

# JWT bearer scheme
security = HTTPBearer(auto_error=False)


def create_access_token(username: str) -> tuple[str, int]:
    """
    Create a JWT access token.

    Returns:
        Tuple of (token_string, expires_in_seconds)
    """
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expire = datetime.now(timezone.utc) + expires_delta

    payload = {
        "sub": username,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )

    return token, int(expires_delta.total_seconds())


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> AdminUser:
    """
    Validate JWT token and return the authenticated admin user.

    Use as a FastAPI dependency on protected routes:
        @router.get("/secret", dependencies=[Depends(get_current_admin)])
    Or to get user info:
        admin: AdminUser = Depends(get_current_admin)
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        username: str | None = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
            )
        return AdminUser(username=username)

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
