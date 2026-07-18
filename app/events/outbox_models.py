import uuid
from enum import Enum

from sqlalchemy import Column, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID

from app.database.connection import Base


class OutboxEventStatus(str, Enum):
    PENDING = "pending"
    PUBLISHING = "publishing"
    PUBLISHED = "published"
    FAILED = "failed"


class OutboxEvent(Base):
    __tablename__ = "outbox_events"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregate_type = Column(String(100), nullable=False)
    aggregate_id = Column(String(255), nullable=False)
    event_type = Column(String(100), nullable=False)
    subject = Column(String(255), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    headers = Column(JSONB, nullable=True)
    status = Column(String(20), nullable=False, default=OutboxEventStatus.PENDING.value, index=True)
    available_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    last_error = Column(Text, nullable=True)
    published_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_outbox_pending", "status", "available_at", "created_at"),
    )
