"""
Product model — catalog of items available for sale.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Product details
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    short_description: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="Brief text for AI catalog queries"
    )

    # Pricing
    price: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    currency: Mapped[str] = mapped_column(String(10), default="CZK", nullable=False)

    # Inventory
    stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Organization
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    tags: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="Comma-separated tags for search"
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Media
    image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    orders = relationship("Order", back_populates="product", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name='{self.name}', price={self.price} {self.currency})>"

    @property
    def is_in_stock(self) -> bool:
        """Check if product is available for purchase."""
        return self.is_active and self.stock > 0
