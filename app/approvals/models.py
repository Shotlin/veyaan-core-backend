import enum
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship

from app.database.connection import Base


class ApprovalStatus(str, enum.Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"


class Approval(Base):
    __tablename__ = "approvals"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    command_id = Column(PG_UUID(as_uuid=True), ForeignKey("commands.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    owner_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    risk_level = Column(String(20), nullable=False)
    action_title = Column(String(255), nullable=False)
    action_description = Column(Text, nullable=False)
    status = Column(SQLEnum(ApprovalStatus, create_constraint=False, native_enum=False), nullable=False, default=ApprovalStatus.PENDING, index=True)
    decision_nonce_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    decision_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    command = relationship("Command", back_populates="approval")
    owner = relationship("User")
