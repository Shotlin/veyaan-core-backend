"""Add device tables

Revision ID: 002
Revises: 001
Create Date: 2024-01-18 00:00:00.000000

"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create devices table
    op.create_table(
        'devices',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('owner_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('device_type', sa.String(100), nullable=False),
        sa.Column('operating_system', sa.String(100), nullable=False),
        sa.Column('app_version', sa.String(50), nullable=False),
        sa.Column('protocol_version', sa.String(20), nullable=False, server_default='v1'),
        sa.Column('device_public_identity', sa.Text(), nullable=False),
        sa.Column('trust_status', sa.String(20), default='trusted', nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Create device_credentials table
    op.create_table(
        'device_credentials',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('device_id', UUID(as_uuid=True), sa.ForeignKey('devices.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('credential_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create pairing_requests table
    op.create_table(
        'pairing_requests',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('device_name', sa.String(255), nullable=False),
        sa.Column('device_type', sa.String(100), nullable=False),
        sa.Column('operating_system', sa.String(100), nullable=False),
        sa.Column('app_version', sa.String(50), nullable=False),
        sa.Column('protocol_version', sa.String(20), nullable=False, server_default='v1'),
        sa.Column('device_public_identity', sa.Text(), nullable=False),
        sa.Column('pairing_code_hash', sa.String(64), nullable=False),
        sa.Column('owner_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('status', sa.String(20), default='pending', nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Add CHECK constraints for enum-like fields
    op.execute("""
        ALTER TABLE devices ADD CONSTRAINT chk_device_type 
        CHECK (device_type IN ('macbook', 'iphone', 'ipad'))
    """)
    op.execute("""
        ALTER TABLE devices ADD CONSTRAINT chk_trust_status 
        CHECK (trust_status IN ('trusted', 'revoked', 'pending'))
    """)
    op.execute("""
        ALTER TABLE pairing_requests ADD CONSTRAINT chk_pairing_status 
        CHECK (status IN ('pending', 'confirmed', 'expired', 'rejected'))
    """)


def downgrade() -> None:
    op.drop_table('pairing_requests')
    op.drop_table('device_credentials')
    op.drop_table('devices')

    # Drop enums (handled by dropping tables with CASCADE)
