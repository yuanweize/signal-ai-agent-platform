"""
Payment model — records payment transactions.

Skeleton for future payment gateway integrations:
- Stripe
- Cryptocurrency (BTC, XMR, etc.)
- 易支付 (YiPay) and similar platforms

Designed with anonymity in mind — minimal PII storage.
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Payment(Base):
    """A payment transaction linked to an order."""

    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    # Link to order
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id"), unique=True, nullable=False, index=True
    )

    # Link to user (denormalized for quick queries)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)

    # Payment gateway: "stripe", "crypto_btc", "crypto_xmr", "yipay", "manual", etc.
    gateway: Mapped[str] = mapped_column(String(50), nullable=False)

    # Gateway-specific transaction ID (opaque, no PII)
    gateway_tx_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)

    # Amount & currency
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), nullable=False)

    # Status: pending → processing → completed → refunded / failed
    status: Mapped[str] = mapped_column(
        String(20), default="pending", nullable=False, index=True
    )

    # Payment address (for crypto — wallet address; for others — masked reference)
    payment_address: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Admin notes (internal only, never exposed to users)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    order = relationship("Order", back_populates="payment")
    user = relationship("User", back_populates="payments")

    def __repr__(self) -> str:
        return (
            f"<Payment(id={self.id}, gateway='{self.gateway}', "
            f"amount={self.amount} {self.currency}, status='{self.status}')>"
        )
