"""
FastAPI application entry point.

Registers lifespan events, CORS, routes, and health check.
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import async_session, close_db, init_db
from app.services.data_retention import cleanup_expired_data
from app.services.metrics import runtime_metrics
from app.services.runtime_config import get_runtime_settings
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
    async with async_session() as session:
        cleanup_result = await cleanup_expired_data(session)
        logger.info(
            "🧹 Retention cleanup: "
            f"messages={cleanup_result['messages_deleted']}, "
            f"conversations={cleanup_result['conversations_deleted']}, "
            f"audit_logs={cleanup_result['audit_logs_deleted']}"
        )

    # Wire up Signal message pipeline
    from app.services.signal_client import signal_client
    from app.services.message_handler import message_handler
    from app.services.ai_engine import ai_engine

    signal_client.on_message = message_handler.handle

    # Start Signal listener (runs in background)
    if settings.signal_phone_number:
        await signal_client.start()
        logger.info("✅ Signal listener started")
    else:
        logger.warning("⚠️  SIGNAL_PHONE_NUMBER not set — listener disabled")

    # Initialize AI engine (only if feature is enabled)
    ai_ok = await ai_engine.initialize()
    if ai_ok:
        message_handler.set_ai_engine(ai_engine)
        logger.info(f"✅ AI engine active — model: {settings.ai_model}")
    else:
        logger.info("ℹ️  Running without AI — messages will be logged only")

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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restricted in production via nginx proxy
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Health Check ----
@app.get("/health", tags=["System"])
async def health_check():
    """Health check with module status for frontend dashboard."""
    bot_name = settings.bot_name
    try:
        async with async_session() as session:
            runtime = await get_runtime_settings(session)
            bot_name = runtime.get("bot_name", bot_name)
    except Exception:
        pass

    return {
        "status": "ok",
        "version": APP_VERSION,
        "bot_name": bot_name,
        "features": settings.features_summary,
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
from app.api.router import api_router
app.include_router(api_router, prefix="/api")
