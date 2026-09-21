"""
FastAPI application entry point.

Registers lifespan events, CORS, routes, and health check.
"""

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.config import settings
from app.database import async_session, close_db, init_db
from app.services.data_retention import cleanup_expired_data
from app.services.metrics import runtime_metrics
from app.services.runtime_config import get_runtime_settings, is_ai_api_key_optional
from app.services.security_bootstrap import get_bootstrap_status
from app.services.signal_client import signal_client
from app.version import get_app_version

# ---- Logging setup ----
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("signal-market-bot")
APP_VERSION = get_app_version()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown lifecycle."""
    logger.info("🚀 Signal Market Bot starting up...")
    logger.info(f"   Signal API:  {settings.signal_api_url}")
    logger.info(f"   Database:    {settings.database_url}")

    # Log feature toggle states
    features = settings.features_summary
    for name, enabled in features.items():
        icon = "✅" if enabled else "⬜"
        logger.info(f"   {icon} {name}: {'enabled' if enabled else 'disabled'}")

    # Initialize database tables
    await init_db()
    logger.info("✅ Database initialized")

    # Startup retention cleanup
    runtime = None
    async with async_session() as session:
        runtime = await get_runtime_settings(session)
        settings.bot_default_language = (
            str(runtime.get("bot_default_language") or settings.bot_default_language).strip()
            or settings.bot_default_language
        )
        await signal_client.apply_runtime_config(
            signal_api_url=str(runtime.get("signal_api_url") or ""),
            signal_api_token=str(runtime.get("signal_api_token") or ""),
            signal_phone_number=str(runtime.get("signal_phone_number") or ""),
            restart_listener=False,
        )
        cleanup_result = await cleanup_expired_data(session)
        logger.info(
            "🧹 Retention cleanup: "
            f"messages={cleanup_result['messages_deleted']}, "
            f"conversations={cleanup_result['conversations_deleted']}, "
            f"audit_logs={cleanup_result['audit_logs_deleted']}"
        )

    # Wire up Signal message pipeline
    from app.services.ai_engine import ai_engine
    from app.services.message_handler import message_handler

    signal_client.on_message = message_handler.handle

    # Start Signal listener (runs in background)
    if settings.signal_api_url and settings.signal_phone_number:
        await signal_client.start()
        logger.info("✅ Signal listener started")
    else:
        logger.warning("⚠️  SIGNAL config incomplete (url/phone) — listener disabled")

    # Initialize AI engine (only if feature is enabled)
    ai_ok = await ai_engine.initialize()
    message_handler.set_ai_engine(ai_engine)
    if ai_ok:
        logger.info(f"✅ AI engine active — model: {settings.ai_model}")
    else:
        logger.info(
            "ℹ️  AI warmup skipped at startup. "
            "Runtime key from Settings can still activate AI on next incoming message."
        )

    yield

    # Shutdown
    logger.info("🛑 Shutting down...")
    await signal_client.stop()
    await close_db()
    logger.info("✅ All services stopped")


# ---- FastAPI App ----
app = FastAPI(
    title="Signal Market Bot",
    description="AI-powered Signal group market bot with admin dashboard",
    version=APP_VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    runtime_metrics.inc("api.requests.total")
    if response.status_code == 401:
        runtime_metrics.inc("api.requests.401")
    if response.status_code >= 500:
        runtime_metrics.inc("api.requests.5xx")
    runtime_metrics.observe_latency("api.request", duration)
    return response


# ---- CORS ----
# In production, restrict origins to configured ALLOWED_ORIGINS env var.
# Default to localhost variants for local development only.
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "").strip()
if _raw_origins:
    _allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]
else:
    # Development fallback — still restrictive, not wildcard
    _allowed_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ---- Health Check ----
@app.get("/health", tags=["System"])
async def health_check():
    """Health check with real subsystem status.

    /health returns actual DB and configuration state.
    A DB failure will reflect in the response but HTTP 200 is still returned
    so load balancers remain happy. Use the `status` field for alerting.
    """
    bot_name = settings.bot_name
    db_ok = False
    migration_ok = False
    runtime_features: dict = {}
    bootstrap_complete = False

    try:
        async with async_session() as session:
            # DB liveness: simple count query
            from sqlalchemy import text

            await session.execute(text("SELECT 1"))
            db_ok = True

            # Migration state check
            try:
                result = await session.execute(
                    text("SELECT version_num FROM alembic_version LIMIT 1")
                )
                row = result.scalar_one_or_none()
                migration_ok = row is not None
            except Exception:
                migration_ok = False

            runtime = await get_runtime_settings(session)
            bootstrap_status = await get_bootstrap_status(session)
            bot_name = runtime.get("bot_name", bot_name)
            ai_base_url = runtime.get("ai_api_base_url") or ""
            ai_enabled = bool(runtime.get("is_ai_enabled")) and (
                bool(runtime.get("has_ai_api_key")) or is_ai_api_key_optional(ai_base_url)
            )
            bootstrap_complete = not bootstrap_status.bootstrap_required
            runtime_features = {
                "signal_configured": bool(
                    runtime.get("signal_api_url") and runtime.get("signal_phone_number")
                ),
                "signal_listener": signal_client.is_connected,
                "ai_configured": ai_enabled,
                "market": bool(runtime.get("is_market_enabled")),
                "admin_2fa": bootstrap_status.requires_2fa,
                "bootstrap_complete": bootstrap_complete,
            }
    except Exception:
        db_ok = False
        runtime_features = {
            "signal_configured": False,
            "signal_listener": False,
            "ai_configured": False,
            "market": False,
            "admin_2fa": False,
            "bootstrap_complete": False,
        }

    overall_status = "ok" if db_ok else "degraded"

    return {
        "status": overall_status,
        "version": APP_VERSION,
        "bot_name": bot_name,
        "db": db_ok,
        "migration_applied": migration_ok,
        "features": runtime_features,
    }


# ---- API Info ----
@app.get("/", tags=["System"])
async def root():
    """API root — basic info."""
    return {
        "name": "Signal Market Bot API",
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/health",
    }


# ---- API Routes ----
app.include_router(api_router, prefix="/api")
