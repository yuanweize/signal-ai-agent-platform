"""
Async SQLAlchemy database engine and session management.

Uses aiosqlite for SQLite async support. Easily swappable to
asyncpg for PostgreSQL by changing DATABASE_URL.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Create async engine
# - SQLite: check_same_thread=False required for async
# - echo=True only in debug mode
_connect_args = {}
if settings.database_url.startswith("sqlite"):
    _connect_args["check_same_thread"] = False

engine = create_async_engine(
    settings.database_url,
    connect_args=_connect_args,
    echo=(settings.log_level == "DEBUG"),
    pool_pre_ping=True,
)

# Session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a database session per request."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Alias for cleaner imports
get_session = get_db


async def init_db() -> None:
    """Create all tables (used in development / first run)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db() -> None:
    """Dispose engine connections on shutdown."""
    await engine.dispose()
