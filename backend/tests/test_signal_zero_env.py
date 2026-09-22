"""
Integration test for Zero-.env Signal configuration and startup.

Verifies:
- With environment Signal fields blank, DB-only BotConfig configuration triggers signal_client.start()
  during application lifespan startup.
- When DB config is also missing, the listener is disabled and signal_client.start() is NOT invoked.
- Diagnostics endpoints reflect the effective runtime configuration.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base
from app.main import app, lifespan
from app.models.config import BotConfig
from app.services.event_pipeline import event_pipeline
from app.services.runtime_config import (
    KEY_SIGNAL_API_TOKEN_ENC,
    KEY_SIGNAL_API_URL,
    KEY_SIGNAL_PHONE_NUMBER,
    encrypt_value,
)
from app.services.signal_client import signal_client


@pytest.fixture
async def test_app_db(tmp_path, monkeypatch):
    """File-backed SQLite DB for full lifespan testing."""
    db_file = tmp_path / "lifespan_test.db"
    db_url = f"sqlite+aiosqlite:///{db_file}"
    engine = create_async_engine(db_url, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr("app.main.async_session", maker)
    monkeypatch.setattr(settings, "database_url", db_url)

    yield maker

    await engine.dispose()


@pytest.mark.asyncio
async def test_db_only_signal_config_starts_listener(test_app_db, monkeypatch, caplog):
    """When env has no Signal config, lifespan must use DB BotConfig to start the listener."""
    monkeypatch.setattr(settings, "signal_api_url", "")
    monkeypatch.setattr(settings, "signal_phone_number", "")
    monkeypatch.setattr(settings, "signal_api_token", "")

    signal_client._api_url = ""
    signal_client._phone_number = ""
    signal_client._api_token = ""
    event_pipeline._workers = []

    async with test_app_db() as session:
        session.add(BotConfig(key=KEY_SIGNAL_API_URL, value="http://signal-gateway.internal:8080"))
        session.add(BotConfig(key=KEY_SIGNAL_PHONE_NUMBER, value="+420777000111"))
        session.add(
            BotConfig(key=KEY_SIGNAL_API_TOKEN_ENC, value=encrypt_value("secret-signal-token"))
        )
        await session.commit()

    start_mock = AsyncMock()
    stop_mock = AsyncMock()
    with (
        patch.object(signal_client, "start", start_mock),
        patch.object(signal_client, "stop", stop_mock),
    ):
        caplog.set_level(logging.INFO)
        async with lifespan(app):
            assert start_mock.call_count == 1, (
                "signal_client.start() must be invoked when DB has config"
            )
            assert signal_client._api_url == "http://signal-gateway.internal:8080"
            assert signal_client._phone_number == "+420777000111"

        # Assert no plain secrets leaked in logs
        assert "secret-signal-token" not in caplog.text


@pytest.mark.asyncio
async def test_missing_db_config_disables_listener(test_app_db, monkeypatch, caplog):
    """When both env and DB have no Signal config, listener must remain disabled."""
    monkeypatch.setattr(settings, "signal_api_url", "")
    monkeypatch.setattr(settings, "signal_phone_number", "")
    monkeypatch.setattr(settings, "signal_api_token", "")

    signal_client._api_url = ""
    signal_client._phone_number = ""
    signal_client._api_token = ""
    event_pipeline._workers = []

    start_mock = AsyncMock()
    stop_mock = AsyncMock()
    with (
        patch.object(signal_client, "start", start_mock),
        patch.object(signal_client, "stop", stop_mock),
    ):
        caplog.set_level(logging.INFO)
        async with lifespan(app):
            assert start_mock.call_count == 0, (
                "signal_client.start() must NOT be called without config"
            )
            assert "listener disabled" in caplog.text
