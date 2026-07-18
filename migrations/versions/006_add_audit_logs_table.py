"""Add audit_logs table

Revision ID: 006
Revises: 005
Create Date: 2024-01-18 00:00:00.000000

"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create audit_logs table
    op.create_table(
        'audit_logs',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('device_id', UUID(as_uuid=True), sa.ForeignKey('devices.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('command_id', UUID(as_uuid=True), sa.ForeignKey('commands.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('approval_id', UUID(as_uuid=True), sa.ForeignKey('approvals.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('category', sa.String(50), nullable=False, index=True),
        sa.Column('action', sa.String(100), nullable=False, index=True),
        sa.Column('result', sa.String(50), nullable=False),
        sa.Column('event_metadata', sa.Text(), nullable=True),
        sa.Column('request_id', sa.String(64), nullable=True, index=True),
        sa.Column('trace_id', sa.String(64), nullable=True, index=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
    )

    # Add CHECK constraints for enum-like fields
    op.execute("""
        ALTER TABLE audit_logs ADD CONSTRAINT chk_audit_category
        CHECK (category IN ('auth', 'device', 'command', 'approval', 'emergency_stop', 'security', 'system'))
    """)
    op.execute("""
        ALTER TABLE audit_logs ADD CONSTRAINT chk_audit_action
        CHECK (action IN (
            'login', 'logout', 'token_refresh',
            'device_pair_started', 'device_pair_confirmed', 'device_revoked', 'device_connected', 'device_disconnected',
            'command_created', 'command_delivered', 'command_acknowledged', 'command_started', 'command_succeeded',
            'command_failed', 'command_cancelled', 'command_expired', 'command_blocked',
            'approval_created', 'approval_approved', 'approval_rejected', 'approval_expired',
            'emergency_stop_activated', 'emergency_stop_released',
            'invalid_token', 'invalid_credential', 'replay_attempt', 'unauthorized_access', 'rate_limit_exceeded',
            'config_changed', 'backup_started', 'backup_completed', 'restore_started', 'restore_completed'
        ))
    """)
    op.execute("""
        ALTER TABLE audit_logs ADD CONSTRAINT chk_audit_result
        CHECK (result IN ('success', 'failure', 'blocked', 'error'))
    """)


def downgrade() -> None:
    op.drop_table('audit_logs')
