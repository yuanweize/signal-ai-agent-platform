"""Campaign-related models for group advertising operations."""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CampaignDeliveryLog(Base):
    """One delivery attempt to a target group for an outbound campaign message."""

    __tablename__ = "campaign_delivery_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    campaign_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    group_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    message_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    details: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return (
            f"<CampaignDeliveryLog(id={self.id}, campaign='{self.campaign_name}', "
            f"group_id='{self.group_id}', status='{self.status}')>"
        )
