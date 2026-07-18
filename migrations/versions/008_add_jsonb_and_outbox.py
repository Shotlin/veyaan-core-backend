"""Add JSONB columns, outbox_events table, and missing fields

Revision ID: 008
Revises: 007
Create Date: 2024-01-19 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = '008'
down_revision = '007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Outbox events table
    op.create_table(
        'outbox_events',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('aggregate_type', sa.String(100), nullable=False),
        sa.Column('aggregate_id', sa.String(255), nullable=False),
        sa.Column('event_type', sa.String(100), nullable=False),
        sa.Column('subject', sa.String(255), nullable=False),
        sa.Column('payload', JSONB, nullable=False, server_default='{}'),
        sa.Column('headers', JSONB, nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending', index=True),
        sa.Column('available_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False, index=True),
        sa.Column('attempt_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text, nullable=True),
        sa.Column('published_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_outbox_pending', 'outbox_events', ['status', 'available_at', 'created_at'])

    # Add attempt_count to pairing_requests
    op.add_column('pairing_requests', sa.Column('attempt_count', sa.Integer, nullable=False, server_default='0'))

    # Add deduplication_key to command_state_events
    op.add_column('command_state_events', sa.Column('deduplication_key', sa.String(64), nullable=True, unique=True))

    # Add request_fingerprint and result_data to commands
    op.add_column('commands', sa.Column('request_fingerprint', sa.String(64), nullable=True))
    op.add_column('commands', sa.Column('result_data', JSONB, nullable=True))

    # Convert commands.parameters from Text to JSONB
    # For existing data, try to parse as JSON, fall back to empty object
    op.execute("""
        ALTER TABLE commands
        ALTER COLUMN parameters TYPE JSONB
        USING CASE
            WHEN parameters IS NULL OR parameters = '' THEN '{}'::jsonb
            WHEN parameters::text LIKE '{%' OR parameters::text LIKE '[%' THEN parameters::jsonb
            ELSE ('{"value": "' || parameters || '"}')::jsonb
        END
    """)
    op.alter_column('commands', 'parameters', nullable=False, server_default='{}')

    # Convert command_state_events.event_metadata from Text to JSONB
    op.execute("""
        ALTER TABLE command_state_events
        ALTER COLUMN event_metadata TYPE JSONB
        USING CASE
            WHEN event_metadata IS NULL THEN NULL
            WHEN event_metadata::text LIKE '{%' OR event_metadata::text LIKE '[%' THEN event_metadata::jsonb
            ELSE ('{"value": "' || event_metadata || '"}')::jsonb
        END
    """)

    # Convert audit_logs.event_metadata from Text to JSONB
    op.execute("""
        ALTER TABLE audit_logs
        ALTER COLUMN event_metadata TYPE JSONB
        USING CASE
            WHEN event_metadata IS NULL THEN NULL
            WHEN event_metadata::text LIKE '{%' OR event_metadata::text LIKE '[%' THEN event_metadata::jsonb
            ELSE ('{"value": "' || event_metadata || '"}')::jsonb
        END
    """)


def downgrade() -> None:
    # Revert audit_logs.event_metadata
    op.alter_column('audit_logs', 'event_metadata', type_=sa.Text, nullable=True)

    # Revert command_state_events.event_metadata
    op.alter_column('command_state_events', 'event_metadata', type_=sa.Text, nullable=True)

    # Revert commands.parameters
    op.alter_column('commands', 'parameters', type_=sa.Text, nullable=False, server_default='{}')

    # Remove columns from commands
    op.drop_column('commands', 'result_data')
    op.drop_column('commands', 'request_fingerprint')

    # Remove deduplication_key from command_state_events
    op.drop_column('command_state_events', 'deduplication_key')

    # Remove attempt_count from pairing_requests
    op.drop_column('pairing_requests', 'attempt_count')

    # Drop outbox_events table
    op.drop_index('ix_outbox_pending', table_name='outbox_events')
    op.drop_table('outbox_events')
