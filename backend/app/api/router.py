"""
API Router — aggregates all API sub-routers under /api prefix.
"""

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.dashboard import router as dashboard_router
from app.api.products import router as products_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(products_router)
api_router.include_router(dashboard_router)
