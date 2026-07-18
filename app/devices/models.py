import enum
import hashlib
import secrets
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database.connection import Base


class DeviceStatus(str, enum.Enum):
    TRUSTED = "trusted"
    REVOKED = "revoked"
    PENDING = "pending"


class PairingStatus(str, enum.Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    REJECTED = "rejected"


class DeviceCredential(Base):
    __tablename__ = "device_credentials"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    device_id = Column(UUID(as_uuid=True), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    credential_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    device = relationship("Device", back_populates="credentials")


class PairingRequest(Base):
    __tablename__ = "pairing_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    device_name = Column(String(255), nullable=False)
    device_type = Column(String(100), nullable=False)
    operating_system = Column(String(100), nullable=False)
    app_version = Column(String(50), nullable=False)
    protocol_version = Column(String(20), nullable=False, default="v1")
    device_public_identity = Column(Text, nullable=False)
    pairing_code_hash = Column(String(64), nullable=False)
    attempt_count = Column(Integer, nullable=False, default=0)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    status = Column(SQLEnum(PairingStatus, create_constraint=False, native_enum=False), default=PairingStatus.PENDING, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    confirmed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Device(Base):
    __tablename__ = "devices"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    display_name = Column(String(255), nullable=False)
    device_type = Column(String(100), nullable=False)
    operating_system = Column(String(100), nullable=False)
    app_version = Column(String(50), nullable=False)
    protocol_version = Column(String(20), nullable=False, default="v1")
    device_public_identity = Column(Text, nullable=False)
    trust_status = Column(SQLEnum(DeviceStatus, create_constraint=False, native_enum=False), default=DeviceStatus.TRUSTED, nullable=False)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    revoked_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    credentials = relationship("DeviceCredential", back_populates="device", cascade="all, delete-orphan")
    owner = relationship("User", back_populates="devices")
    commands = relationship("Command", back_populates="device", cascade="all, delete-orphan")

    @staticmethod
    def generate_pairing_code() -> tuple[str, str]:
        """Generate a pairing code and its hash."""
        code = secrets.token_urlsafe(16)
        code_hash = hashlib.sha256(code.encode()).hexdigest()
        return code, code_hash

    @staticmethod
    def hash_credential(credential: str) -> str:
        return hashlib.sha256(credential.encode()).hexdigest()

    @staticmethod
    def generate_credential() -> tuple[str, str]:
        """Generate a device credential and its hash."""
        credential = secrets.token_urlsafe(32)
        credential_hash = hashlib.sha256(credential.encode()).hexdigest()
        return credential, credential_hash
