import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Add the app directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

import app.database.models  # noqa: F401 - ensure all models are loaded for autogeneration
from app.config import settings
from app.database.connection import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.DATABASE_URL
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        process_revision_directives=filter_ops,
    )


    with context.begin_transaction():
        context.run_migrations()


def filter_ops(context, revision, directives):
    if not directives:
        return
    script = directives[0]

    def is_false_positive(op):
        op_name = op.__class__.__name__
        if op_name in ("CreateIndexOp", "DropIndexOp") and getattr(op, "table_name", None) == "notification_records":
            return True
        if op_name == "DropConstraintOp" and getattr(op, "constraint_name", None) == "users_supabase_user_id_key":
            return True
        if op_name == "AlterColumnOp":
            t_name = getattr(op, "table_name", None)
            c_name = getattr(op, "column_name", None)
            if t_name == "approvals" and c_name == "status":
                return True
            if t_name == "devices" and c_name == "trust_status":
                return True
            if t_name == "pairing_requests" and c_name == "status":
                return True
            if t_name == "tasks" and c_name == "attempt_count":
                return True
            if t_name == "users" and c_name == "status":
                return True
        return False

    filtered_ops = []
    for op in script.upgrade_ops.ops:
        if op.__class__.__name__ == "ModifyTableOps":
            op.ops = [sub_op for sub_op in op.ops if not is_false_positive(sub_op)]
            if op.ops:
                filtered_ops.append(op)
        else:
            if not is_false_positive(op):
                filtered_ops.append(op)

    script.upgrade_ops.ops = filtered_ops


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        process_revision_directives=filter_ops,
    )

    with context.begin_transaction():
        context.run_migrations()



async def run_async_migrations() -> None:
    """In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Use our settings directly
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = settings.DATABASE_URL

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    import asyncio

    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
