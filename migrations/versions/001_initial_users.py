"""Initial migration - create users table

Revision ID: 001
Revises:
Create Date: 2024-01-18 00:00:00.000000

"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create users table
    op.create_table(
        'users',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('supabase_user_id', sa.String(255), nullable=False, unique=True),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=False),
        sa.Column('status', sa.Enum('active', 'inactive', 'suspended', name='user_status'), nullable=False, server_default='active'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )

    # Create index on supabase_user_id
    op.create_index('ix_users_supabase_user_id', 'users', ['supabase_user_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_users_supabase_user_id', table_name='users')
    op.drop_table('users')

    # Drop enum type
    user_status_enum = sa.Enum('active', 'inactive', 'suspended', name='user_status')
    user_status_enum.drop(op.get_bind(), checkfirst=True)
