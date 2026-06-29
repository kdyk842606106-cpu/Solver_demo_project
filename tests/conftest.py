"""
Pytest configuration for database tests.

Provides fixtures for creating test database sessions.
Patches PostgreSQL-specific column types (JSONB, ARRAY) for SQLite compatibility.
"""

import pytest
import pytest_asyncio
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Base,
    Machine,
    MachineState,
    MachineStateFeature,
    MachineType,
    OpRule,
    OpRuleEffect,
    OpRulePrecond,
    OpRuleResourceReq,
    Resource,
    StateFeatureDef,
)
from app.db.session import Base as SessionBase, get_db_session, patch_sqlite_types


# ============================================================
# SQLite compatibility: patch PostgreSQL-specific column types
# ============================================================

patch_sqlite_types(force=True)


# Use in-memory SQLite for testing
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

# Shared test engine for HTTP client tests
_shared_test_engine = create_async_engine(
    TEST_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

_shared_test_session_factory = async_sessionmaker(
    bind=_shared_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency override for get_db_session — uses test engine."""
    async with _shared_test_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# ============================================================
# Core fixtures
# ============================================================


@pytest_asyncio.fixture(autouse=True)
async def setup_db():
    """Create all tables before each test, drop after."""
    async with _shared_test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _shared_test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Raw session for seeding data in tests."""
    async with _shared_test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator:
    """httpx AsyncClient wired to the FastAPI app with test DB."""
    from httpx import ASGITransport, AsyncClient
    from app.main import app

    app.dependency_overrides[get_db_session] = _override_get_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def async_engine():
    """Create async test engine (shared with client fixture)."""
    yield _shared_test_engine


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


async def _seed_integration_data(session: AsyncSession) -> None:
    """Seed data for planner integration tests — mirrors seeds/001_initial_data.sql."""
    session.add(MachineType(id=1, code="CNC_LATHE", name="CNC Lathe"))
    session.add_all([
        StateFeatureDef(id=1, machine_type_id=1, feature_key="temperature_level",
                        feature_name="Temperature Level", value_type="enum"),
        StateFeatureDef(id=2, machine_type_id=1, feature_key="clean_level",
                        feature_name="Clean Level", value_type="enum"),
        StateFeatureDef(id=3, machine_type_id=1, feature_key="calibration",
                        feature_name="Calibration Status", value_type="enum"),
    ])
    session.add(Machine(id=1, machine_type_id=1, code="M-001",
                        name="Main CNC Lathe", location="Workshop A"))
    session.add_all([
        Resource(id=1, machine_id=1, code="TECH-01", name="Technician Alice",
                 resource_type="TECHNICIAN", capacity=1, is_available=True),
        Resource(id=2, machine_id=1, code="TECH-02", name="Technician Bob",
                 resource_type="TECHNICIAN", capacity=1, is_available=True),
        Resource(id=3, machine_id=1, code="CLEAN-01", name="Cleaning Robot",
                 resource_type="CLEANER", capacity=1, is_available=True),
    ])

    session.add(MachineState(id=1, machine_id=1, state_type="current",
                             label="Cold Standby State"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=1, feature_key="temperature_level",
                            feature_value="cold"),
        MachineStateFeature(machine_state_id=1, feature_key="clean_level",
                            feature_value="dirty"),
        MachineStateFeature(machine_state_id=1, feature_key="calibration",
                            feature_value="off"),
    ])

    session.add(MachineState(id=2, machine_id=1, state_type="target",
                             label="Ready for Production"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=2, feature_key="temperature_level",
                            feature_value="hot"),
        MachineStateFeature(machine_state_id=2, feature_key="clean_level",
                            feature_value="clean"),
        MachineStateFeature(machine_state_id=2, feature_key="calibration",
                            feature_value="on"),
    ])

    session.add(OpRule(id=1, machine_type_id=1, code="OP_WARMUP",
                       name="Warm Up Machine", duration_min=30, is_active=True))
    session.add(OpRulePrecond(op_rule_id=1, feature_key="temperature_level",
                              operator="eq", feature_value="cold"))
    session.add(OpRuleEffect(op_rule_id=1, feature_key="temperature_level",
                             new_value="hot"))
    session.add(OpRuleResourceReq(op_rule_id=1, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    session.add(OpRule(id=2, machine_type_id=1, code="OP_CLEANING",
                       name="Clean Machine", duration_min=20, is_active=True))
    session.add(OpRulePrecond(op_rule_id=2, feature_key="clean_level",
                              operator="eq", feature_value="dirty"))
    session.add(OpRuleEffect(op_rule_id=2, feature_key="clean_level",
                             new_value="clean"))
    session.add(OpRuleResourceReq(op_rule_id=2, resource_type="CLEANER",
                                  quantity=1, is_required=True))

    session.add(OpRule(id=3, machine_type_id=1, code="OP_CALIBRATE",
                       name="Calibrate Machine", duration_min=15, is_active=True))
    session.add(OpRulePrecond(op_rule_id=3, feature_key="temperature_level",
                              operator="eq", feature_value="hot"))
    session.add(OpRulePrecond(op_rule_id=3, feature_key="calibration",
                              operator="eq", feature_value="off"))
    session.add(OpRuleEffect(op_rule_id=3, feature_key="calibration",
                             new_value="on"))
    session.add(OpRuleResourceReq(op_rule_id=3, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    session.add(OpRule(id=4, machine_type_id=1, code="OP_COOLDOWN",
                       name="Cool Down Machine", duration_min=25, is_active=True))
    session.add(OpRulePrecond(op_rule_id=4, feature_key="temperature_level",
                              operator="eq", feature_value="hot"))
    session.add(OpRuleEffect(op_rule_id=4, feature_key="temperature_level",
                             new_value="cold"))
    session.add(OpRuleResourceReq(op_rule_id=4, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    session.add(OpRule(id=5, machine_type_id=1, code="OP_INSPECT",
                       name="Inspect Machine", duration_min=10, is_active=True))
    session.add(OpRuleResourceReq(op_rule_id=5, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    await session.commit()


@pytest_asyncio.fixture
async def integration_session(async_engine):
    """Async test session pre-seeded with planner integration test data."""
    async_session_maker = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session_maker() as session:
        await _seed_integration_data(session)
        yield session
