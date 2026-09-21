"""
Shared API dependencies — authentication and database session.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_session
from app.schemas.auth import AdminUser
from app.services.security_bootstrap import get_admin_username, get_jwt_signing_secret

# JWT bearer scheme
security = HTTPBearer(auto_error=False)


async def create_access_token(username: str, session: AsyncSession) -> tuple[str, int]:
    """
    Create a JWT access token.

    Returns:
        Tuple of (token_string, expires_in_seconds)
    """
    expires_delta = timedelta(minutes=settings.jwt_expire_minutes)
    expire = datetime.now(UTC) + expires_delta

    payload = {
        "sub": username,
        "exp": expire,
        "iat": datetime.now(UTC),
    }

    token = jwt.encode(
        payload,
        await get_jwt_signing_secret(session),
        algorithm=settings.jwt_algorithm,
    )

    return token, int(expires_delta.total_seconds())


async def get_current_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    session: AsyncSession = Depends(get_session),
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
            await get_jwt_signing_secret(session),
            algorithms=[settings.jwt_algorithm],
        )
        username: str | None = payload.get("sub")
        if username is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token: missing subject",
            )
        configured_username = await get_admin_username(session)
        if username != configured_username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token subject",
            )
        return AdminUser(username=username)

    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
