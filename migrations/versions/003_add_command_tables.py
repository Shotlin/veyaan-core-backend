"""Add command tables

Revision ID: 003
Revises: 002
Create Date: 2024-01-18 00:00:00.000000

"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create commands table
    op.create_table(
        'commands',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('device_id', UUID(as_uuid=True), sa.ForeignKey('devices.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('command_type', sa.String(100), nullable=False, index=True),
        sa.Column('parameters', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('risk_level', sa.String(20), nullable=False, server_default='low'),
        sa.Column('idempotency_key', sa.String(255), nullable=False, index=True),
        sa.Column('state', sa.String(50), nullable=False, server_default='received', index=True),
        sa.Column('requires_approval', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('delayed_execution_allowed', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True, index=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result_summary', sa.Text(), nullable=True),
        sa.Column('error_code', sa.String(50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint('device_id', 'idempotency_key', name='uq_device_idempotency'),
    )

    # Create tasks table
    op.create_table(
        'tasks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('command_id', UUID(as_uuid=True), sa.ForeignKey('commands.id', ondelete='CASCADE'), nullable=False, unique=True, index=True),
        sa.Column('state', sa.String(50), nullable=False, server_default='pending', index=True),
        sa.Column('attempt_count', sa.String(), nullable=False, server_default='0'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('result_summary', sa.Text(), nullable=True),
        sa.Column('error_code', sa.String(50), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
    )

    # Create command_state_events table
    op.create_table(
        'command_state_events',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('command_id', UUID(as_uuid=True), sa.ForeignKey('commands.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('previous_state', sa.String(50), nullable=True),
        sa.Column('new_state', sa.String(50), nullable=False),
        sa.Column('event_source', sa.String(50), nullable=False),
        sa.Column('metadata', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Add CHECK constraints for enum-like fields
    op.execute("""
        ALTER TABLE commands ADD CONSTRAINT chk_risk_level 
        CHECK (risk_level IN ('low', 'medium', 'high', 'prohibited'))
    """)
    op.execute("""
        ALTER TABLE commands ADD CONSTRAINT chk_command_state 
        CHECK (state IN ('received', 'validated', 'awaiting_approval', 'approved', 'rejected', 'queued', 'delivered', 'acknowledged', 'running', 'succeeded', 'failed', 'timed_out', 'cancelled', 'expired', 'blocked_by_emergency_stop'))
    """)
    op.execute("""
        ALTER TABLE tasks ADD CONSTRAINT chk_task_state 
        CHECK (state IN ('pending', 'queued', 'delivered', 'acknowledged', 'running', 'succeeded', 'failed', 'timed_out', 'cancelled'))
    """)
    op.execute("""
        ALTER TABLE command_state_events ADD CONSTRAINT chk_event_state 
        CHECK (new_state IN ('received', 'validated', 'awaiting_approval', 'approved', 'rejected', 'queued', 'delivered', 'acknowledged', 'running', 'succeeded', 'failed', 'timed_out', 'cancelled', 'expired', 'blocked_by_emergency_stop'))
    """)


def downgrade() -> None:
    op.drop_table('command_state_events')
    op.drop_table('tasks')
    op.drop_table('commands')
