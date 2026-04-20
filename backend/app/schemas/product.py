"""
Product schemas — request/response models for the Product CRUD API.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    """Create a new product."""

    name: str = Field(min_length=1, max_length=200)
    description: str = ""
    price: float = Field(ge=0)
    currency: str = "CZK"
    category: str = ""
    tags: str = ""  # Comma-separated tags
    stock: int = Field(ge=0, default=0)
    is_active: bool = True


class ProductUpdate(BaseModel):
    """Update an existing product (partial update)."""

    name: str | None = None
    description: str | None = None
    price: float | None = Field(ge=0, default=None)
    currency: str | None = None
    category: str | None = None
    tags: str | None = None
    stock: int | None = Field(ge=0, default=None)
    is_active: bool | None = None


class ProductResponse(BaseModel):
    """Product data returned by the API."""

    id: int
    name: str
    description: str
    price: float
    currency: str
    category: str
    tags: str
    stock: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductListResponse(BaseModel):
    """Paginated product list."""

    items: list[ProductResponse]
    total: int
    page: int
    page_size: int
