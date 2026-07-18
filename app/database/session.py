from contextlib import asynccontextmanager

from app.database.connection import async_session_maker


@asynccontextmanager
async def get_db_session():
    """Context manager for database sessions."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
