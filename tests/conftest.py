"""
Pytest configuration for database tests.

Provides fixtures for creating test database sessions.
Patches PostgreSQL-specific column types (JSONB, ARRAY) for SQLite compatibility.
"""

import pytest
import pytest_asyncio
from sqlalchemy import JSON
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Base,
    CandidatePlanStep,
    Resource,
    ScheduleResult,
    SolveRequest,
    StateFeatureDef,
)
from app.db.session import Base as SessionBase


# ============================================================
# SQLite compatibility: patch PostgreSQL-specific column types
# ============================================================

CandidatePlanStep.__table__.c.predecessor_ids.type = JSON()
StateFeatureDef.__table__.c.allowed_values.type = JSON()
Resource.__table__.c.meta.type = JSON()
SolveRequest.__table__.c.overrides.type = JSON()
ScheduleResult.__table__.c.tasks.type = JSON()


# Use in-memory SQLite for testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def async_engine():
    """Create async test engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine):
    """Create async test session."""
    async_session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        yield session
