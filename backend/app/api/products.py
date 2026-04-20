"""
Product CRUD API — admin-protected endpoints for catalog management.

All routes require JWT authentication.
Only available when FEATURE_MARKET_ENABLED=true.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AdminUser, get_current_admin
from app.config import settings
from app.database import get_session
from app.models.product import Product
from app.schemas.product import (
    ProductCreate,
    ProductListResponse,
    ProductResponse,
    ProductUpdate,
)

logger = logging.getLogger("api.products")

router = APIRouter(prefix="/products", tags=["Products"])


def _check_market_enabled():
    """Raise 403 if market module is disabled."""
    if not settings.is_market_available:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Market module is disabled (FEATURE_MARKET_ENABLED=false)",
        )


@router.get("", response_model=ProductListResponse)
async def list_products(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = None,
    active_only: bool = True,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """List products with pagination and optional filtering."""
    _check_market_enabled()

    query = select(Product)

    if active_only:
        query = query.where(Product.is_active == True)  # noqa: E712
    if category:
        query = query.where(Product.category == category)

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = (await session.execute(count_query)).scalar() or 0

    # Paginate
    offset = (page - 1) * page_size
    query = query.order_by(Product.created_at.desc()).offset(offset).limit(page_size)
    result = await session.execute(query)
    products = result.scalars().all()

    return ProductListResponse(
        items=[ProductResponse.model_validate(p) for p in products],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: int,
    session: AsyncSession = Depends(get_session),
    _admin: AdminUser = Depends(get_current_admin),
):
    """Get a single product by ID."""
    _check_market_enabled()

    result = await session.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    return ProductResponse.model_validate(product)


@router.post("", response_model=ProductResponse, status_code=201)
async def create_product(
    data: ProductCreate,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Create a new product."""
    _check_market_enabled()

    product = Product(**data.model_dump())
    session.add(product)
    await session.commit()
    await session.refresh(product)

    logger.info(f"📦 Product created: {product.name} (#{product.id}) by {admin.username}")
    return ProductResponse.model_validate(product)


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: int,
    data: ProductUpdate,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Update an existing product (partial update)."""
    _check_market_enabled()

    result = await session.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    # Apply only provided fields
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)

    await session.commit()
    await session.refresh(product)

    logger.info(f"📝 Product updated: {product.name} (#{product.id}) by {admin.username}")
    return ProductResponse.model_validate(product)


@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: int,
    session: AsyncSession = Depends(get_session),
    admin: AdminUser = Depends(get_current_admin),
):
    """Delete a product (hard delete)."""
    _check_market_enabled()

    result = await session.execute(
        select(Product).where(Product.id == product_id)
    )
    product = result.scalar_one_or_none()

    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    name = product.name
    await session.delete(product)
    await session.commit()

    logger.info(f"🗑️  Product deleted: {name} (#{product_id}) by {admin.username}")
