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


def patch_sqlite_types(force: bool = False):
    """Patch PostgreSQL-specific column types for SQLite compatibility.

    SQLAlchemy's ARRAY and JSONB types don't work with SQLite.
    This function detects SQLite URLs and patches the column types
    to JSON (which SQLite supports via TEXT with JSON serialization).
    """
    url = str(db_settings.async_url)
    if 'sqlite' not in url.lower() and not force:
        return

    import logging
    logger = logging.getLogger(__name__)
    logger.info("SQLite detected — patching PostgreSQL-specific column types")

    from sqlalchemy import JSON, Numeric as sa_Numeric
    from app.db import models

    json_columns = [
        models.MachineType.__table__.c.scheduling_config,
        models.CandidatePlanStep.__table__.c.predecessor_ids,
        models.StateFeatureDef.__table__.c.allowed_values,
        models.OpRulePrecond.__table__.c.value_list,
        models.Resource.__table__.c.meta,
        models.FeatureDefinition.__table__.c.allowed_values,
        models.ActivityNode.__table__.c.metadata_json,
        models.AtomicActivity.__table__.c.metadata_json,
        models.ActivityPackageAtomicRef.__table__.c.metadata_json,
        models.StateNode.__table__.c.metadata_json,
        models.StateNodeReference.__table__.c.metadata_json,
        models.ActivityStateBinding.__table__.c.covered_leaf_state_ids,
        models.ActivityStateBinding.__table__.c.metadata_json,
        models.ScopeGuard.__table__.c.metadata_json,
        models.ScopeGuardPrecond.__table__.c.value_list,
        models.MaintenanceIntentTemplate.__table__.c.target_state_node_ids,
        models.MaintenanceIntentTemplate.__table__.c.candidate_activity_scope_ids,
        models.MaintenanceIntentTemplate.__table__.c.observed_fact_templates,
        models.MaintenanceIntentTemplate.__table__.c.desired_fact_templates,
        models.MaintenanceIntentTemplate.__table__.c.metadata_json,
        models.SolveRequest.__table__.c.overrides,
        models.SolveRequest.__table__.c.objectives,
        models.SolveRequest.__table__.c.constraints,
        models.SolveRequest.__table__.c.blockage_constraints,
        models.SolveRequest.__table__.c.calendar_snapshot,
        models.CandidatePlan.__table__.c.adjustment_snapshot,
        models.ScheduleResult.__table__.c.tasks,
        models.PlanAdjustment.__table__.c.scope_step_ids,
        models.PlanAdjustment.__table__.c.constraints,
        models.PlanAdjustment.__table__.c.remove_inherited_constraint_ids,
        models.PlanAdjustment.__table__.c.effective_constraints,
        models.PlanAdjustment.__table__.c.preview_summary,
        models.PlanAdjustment.__table__.c.diagnostics,
        models.WorkCalendarRevision.__table__.c.weekly_windows,
        models.WorkCalendarRevision.__table__.c.date_exceptions,
    ]
    for column in json_columns:
        column.type = JSON()
    # Numeric parent_plan_id for SQLite compatibility
    models.CandidatePlan.__table__.c.parent_plan_id.type = sa_Numeric()

    logger.info("SQLite type patches applied")


# ============================================================
# Async Engine and Session (for FastAPI application)
# ============================================================

async_engine = create_async_engine(
    db_settings.async_url,
    echo=False,  # Set to True for SQL debugging
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    connect_args={"timeout": db_settings.db_connect_timeout},
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
    connect_args={"connect_timeout": db_settings.db_connect_timeout},
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
