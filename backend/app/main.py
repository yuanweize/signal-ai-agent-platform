"""
FastAPI application entry point.

Registers lifespan events, CORS, routes, and health check.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import close_db, init_db

# ---- Logging setup ----
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("signal-market-bot")


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
    version="0.1.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

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
    return {
        "status": "ok",
        "version": "0.1.0",
        "bot_name": settings.bot_name,
        "features": settings.features_summary,
    }


# ---- API Info ----
@app.get("/", tags=["System"])
async def root():
    """API root — basic info."""
    return {
        "name": "Signal Market Bot API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": "/health",
    }


# ---- API Routes ----
from app.api.router import api_router
app.include_router(api_router, prefix="/api")
