"""
Database Session Management

Async SQLAlchemy session with connection pooling.
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import async_session_factory, engine
from app.utils.logging import get_logger

logger = get_logger("db.session")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency for database session.
    Handles commit/rollback automatically.
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Database session error: {e}", exc_info=True)
            await session.rollback()
            raise
        finally:
            await session.close()


@asynccontextmanager
async def get_session_context() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for database session.
    Use for non-FastAPI contexts (e.g., Celery tasks).
    """
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Database session error: {e}", exc_info=True)
            await session.rollback()
            raise


async def init_db() -> None:
    """Initialize database - create tables if not exist."""
    from app.models.base import Base
    from app.models.document import Document, Chunk
    from app.models.tenant import Tenant

    logger.info("Initializing database...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database initialized")


async def close_db() -> None:
    """Close database connections."""
    logger.info("Closing database connections...")
    await engine.dispose()
    logger.info("Database connections closed")


async def check_db_connection() -> bool:
    """Check if database is accessible."""
    try:
        async with async_session_factory() as session:
            await session.execute("SELECT 1")
        return True
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        return False