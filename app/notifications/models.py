"""Notification records model — GAP-P1-11."""

import uuid

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.database.connection import Base


class NotificationRecord(Base):
    """
    Tracks internal notification events and their delivery status.

    Spec reference: section 2.13 — Notification records required fields.
    The service does not require production Firebase/APNS config in Project 1;
    it stores delivery metadata and status for test/audit purposes.
    """

    __tablename__ = "notification_records"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notification_type = Column(String(100), nullable=False, index=True)
    channel = Column(String(50), nullable=False)  # e.g. "push", "internal", "email"
    status = Column(String(20), nullable=False, default="pending", index=True)
    payload = Column(JSONB, nullable=True)  # safe, non-sensitive notification data
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
