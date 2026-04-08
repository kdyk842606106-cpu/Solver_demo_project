"""
Database session management module.

Provides async session factory for FastAPI dependency injection
and sync engine for Alembic migrations.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy import create_engine

from app.db.config import db_settings


# ============================================================
# Async Engine and Session (for FastAPI application)
# ============================================================

async_engine = create_async_engine(
    db_settings.async_url,
    echo=False,  # Set to True for SQL debugging
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency injection for async database sessions.

    Usage:
        @router.post("/solve")
        async def solve(request: SolveRequest, db: AsyncSession = Depends(get_db_session)):
            ...

    Yields:
        AsyncSession: Database session that auto-closes after request.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ============================================================
# Sync Engine and Session (for Alembic migrations and scripts)
# ============================================================

sync_engine = create_engine(
    db_settings.sync_url,
    echo=False,
    pool_pre_ping=True,
)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


def get_sync_session() -> Session:
    """
    Context manager for sync database sessions.

    Usage:
        with get_sync_session() as session:
            result = session.execute(query)
    """
    return SyncSessionLocal()


# ============================================================
# Base Model for ORM
# ============================================================

class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass
