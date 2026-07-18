"""Add approvals table

Revision ID: 004
Revises: 003
Create Date: 2024-01-18 00:00:00.000000

"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create approvals table
    op.create_table(
        'approvals',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('command_id', UUID(as_uuid=True), sa.ForeignKey('commands.id', ondelete='CASCADE'), nullable=False, unique=True, index=True),
        sa.Column('owner_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('risk_level', sa.String(20), nullable=False),
        sa.Column('action_title', sa.String(255), nullable=False),
        sa.Column('action_description', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), default='pending', nullable=False, index=True),
        sa.Column('decision_nonce_hash', sa.String(64), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('decision_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Add CHECK constraints for enum-like fields
    op.execute("""
        ALTER TABLE approvals ADD CONSTRAINT chk_approval_risk_level 
        CHECK (risk_level IN ('low', 'medium', 'high', 'prohibited'))
    """)
    op.execute("""
        ALTER TABLE approvals ADD CONSTRAINT chk_approval_status 
        CHECK (status IN ('pending', 'approved', 'rejected', 'expired'))
    """)


def downgrade() -> None:
    op.drop_table('approvals')
