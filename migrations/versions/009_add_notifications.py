"""Add notification_records table.

Revision ID: 009_add_notifications
Revises: 008_add_jsonb_and_outbox
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "009_add_notifications"
down_revision = "008_add_jsonb_and_outbox"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_records",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("notification_type", sa.String(100), nullable=False),
        sa.Column("channel", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("payload", JSONB, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notification_records_user_id", "notification_records", ["user_id"])
    op.create_index("ix_notification_records_type", "notification_records", ["notification_type"])
    op.create_index("ix_notification_records_status", "notification_records", ["status"])
    op.create_index("ix_notification_records_created_at", "notification_records", ["created_at"])


def downgrade() -> None:
    op.drop_table("notification_records")
