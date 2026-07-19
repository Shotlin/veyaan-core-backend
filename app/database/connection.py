import asyncio
import os
import sys
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.config import settings


class Base(DeclarativeBase):
    pass


_engines = {}


def get_engine():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop not in _engines:
        pool_kwargs = {}
        if "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ:
            pool_kwargs["poolclass"] = NullPool
        else:
            pool_kwargs["pool_size"] = settings.DATABASE_POOL_SIZE
            pool_kwargs["max_overflow"] = settings.DATABASE_MAX_OVERFLOW
            pool_kwargs["pool_pre_ping"] = True

        _engines[loop] = create_async_engine(
            settings.DATABASE_URL,
            echo=settings.ENVIRONMENT == "development",
            **pool_kwargs
        )
    return _engines[loop]


class EngineProxy:
    def __getattr__(self, name):
        return getattr(get_engine(), name)

    def __repr__(self):
        return repr(get_engine())


engine = EngineProxy()

# Standard async_sessionmaker bound to the EngineProxy
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> AsyncSession:
    async with async_session_maker() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """Initialize database connection. Schema managed by Alembic only."""
    async with engine.begin() as conn:
        from sqlalchemy import text

        await conn.execute(text("SELECT 1"))


async def close_db():
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop in _engines:
        await _engines[loop].dispose()
        del _engines[loop]


async def cleanup_all_engines():
    for loop, eng in list(_engines.items()):
        try:
            await eng.dispose()
        except Exception:
            pass
    _engines.clear()
