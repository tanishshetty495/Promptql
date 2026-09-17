"""
Database initialization script.
"""
import asyncio
import logging
from backend.db.base import init_db, engine
from backend.core.logger import app_logger

async def main():
    """Initialize the database."""
    try:
        app_logger.info("Initializing database...")
        await init_db()
        app_logger.info("Database initialized successfully!")
    except Exception as e:
        app_logger.error(f"Failed to initialize database: {e}")
        raise
    finally:
        await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())