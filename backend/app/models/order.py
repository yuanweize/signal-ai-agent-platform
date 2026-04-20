"""
Order model — tracks customer purchases.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Foreign keys
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False, index=True)

    # Order details
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False, comment="Price at time of order")
    total_price: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="CZK", nullable=False)

    # Status: pending → confirmed → paid → shipped → delivered / cancelled
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )

    # Notes (customer message, delivery instructions, etc.)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Which group the order originated from (NULL = DM)
    group_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user = relationship("User", back_populates="orders")
    product = relationship("Product", back_populates="orders")
    payment = relationship("Payment", back_populates="order", uselist=False, lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<Order(id={self.id}, user={self.user_id}, "
            f"product={self.product_id}, status='{self.status}')>"
        )
