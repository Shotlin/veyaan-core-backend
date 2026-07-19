import asyncio
import os
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text
from app.config import settings

async def drop_all():
    print(f"Connecting to: {settings.DATABASE_URL}")
    engine = create_async_engine(settings.DATABASE_URL)
    
    async with engine.begin() as conn:
        # Drop all tables, views, triggers, functions in public schema
        print("Dropping public schema...")
        await conn.execute(text("DROP SCHEMA public CASCADE;"))
        print("Recreating public schema...")
        await conn.execute(text("CREATE SCHEMA public;"))
        await conn.execute(text("GRANT ALL ON SCHEMA public TO public;"))
    
    await engine.dispose()
    print("Database cleaned successfully.")

if __name__ == "__main__":
    asyncio.run(drop_all())
