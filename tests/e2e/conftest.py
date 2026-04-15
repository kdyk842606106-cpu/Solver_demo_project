"""
E2E test configuration.

Provides FastAPI test client with in-memory SQLite database,
seeded with test data for full end-to-end testing.

PostgreSQL-specific types (ARRAY) are patched to JSON for SQLite compatibility.
"""

import pytest
import pytest_asyncio
from collections.abc import AsyncGenerator

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.db.models import (
    Base,
    CandidatePlanStep,
    Machine,
    MachineState,
    MachineStateFeature,
    MachineType,
    OpRule,
    OpRuleEffect,
    OpRulePrecond,
    OpRuleResourceReq,
    Resource,
    SolveRequest,
    StateFeatureDef,
)
from sqlalchemy import JSON

SolveRequest.__table__.c.overrides.type = JSON()
SolveRequest.__table__.c.objectives.type = JSON()
SolveRequest.__table__.c.constraints.type = JSON()
SolveRequest.__table__.c.blockage_constraints.type = JSON()
from app.db.session import get_db_session


# Type patches (JSONB/ARRAY → JSON for SQLite) are in tests/conftest.py


# ============================================================
# Test engine (in-memory SQLite, single connection via StaticPool)
# ============================================================

_test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

_test_session_factory = async_sessionmaker(
    bind=_test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def _override_get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency override for get_db_session — uses test engine."""
    async with _test_session_factory() as session:
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
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with _test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    """Raw session for seeding data in tests."""
    async with _test_session_factory() as session:
        yield session


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    """httpx AsyncClient wired to the FastAPI app with test DB."""
    from app.main import app

    app.dependency_overrides[get_db_session] = _override_get_db_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


# ============================================================
# Seed helpers
# ============================================================


async def seed_base_data(session: AsyncSession) -> None:
    """Machine type, machine instance, feature defs, and resources."""
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
        Resource(id=1, code="TECH-01", name="Technician Alice",
                 resource_type="TECHNICIAN", capacity=1, is_available=True),
        Resource(id=2, code="TECH-02", name="Technician Bob",
                 resource_type="TECHNICIAN", capacity=1, is_available=True),
        Resource(id=3, code="CLEAN-01", name="Cleaning Robot",
                 resource_type="CLEANER", capacity=1, is_available=True),
    ])
    await session.commit()


async def seed_op_rules(session: AsyncSession) -> None:
    """All 5 operation rules with preconditions, effects, resource reqs."""

    # OP_WARMUP: cold → hot (30 min, TECHNICIAN)
    session.add(OpRule(id=1, machine_type_id=1, code="OP_WARMUP",
                       name="Warm Up Machine", duration_min=30, is_active=True))
    session.add(OpRulePrecond(op_rule_id=1, feature_key="temperature_level",
                              operator="eq", feature_value="cold"))
    session.add(OpRuleEffect(op_rule_id=1, feature_key="temperature_level",
                             new_value="hot"))
    session.add(OpRuleResourceReq(op_rule_id=1, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    # OP_CLEANING: dirty → clean (20 min, CLEANER)
    session.add(OpRule(id=2, machine_type_id=1, code="OP_CLEANING",
                       name="Clean Machine", duration_min=20, is_active=True))
    session.add(OpRulePrecond(op_rule_id=2, feature_key="clean_level",
                              operator="eq", feature_value="dirty"))
    session.add(OpRuleEffect(op_rule_id=2, feature_key="clean_level",
                             new_value="clean"))
    session.add(OpRuleResourceReq(op_rule_id=2, resource_type="CLEANER",
                                  quantity=1, is_required=True))

    # OP_CALIBRATE: off → on (15 min, TECHNICIAN, requires hot)
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

    # OP_COOLDOWN: hot → cold (25 min, TECHNICIAN)
    session.add(OpRule(id=4, machine_type_id=1, code="OP_COOLDOWN",
                       name="Cool Down Machine", duration_min=25, is_active=True))
    session.add(OpRulePrecond(op_rule_id=4, feature_key="temperature_level",
                              operator="eq", feature_value="hot"))
    session.add(OpRuleEffect(op_rule_id=4, feature_key="temperature_level",
                             new_value="cold"))
    session.add(OpRuleResourceReq(op_rule_id=4, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    # OP_INSPECT: no state change (10 min, TECHNICIAN)
    session.add(OpRule(id=5, machine_type_id=1, code="OP_INSPECT",
                       name="Inspect Machine", duration_min=10, is_active=True))
    session.add(OpRuleResourceReq(op_rule_id=5, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    await session.commit()


async def seed_serial_states(session: AsyncSession) -> None:
    """
    States for serial-only scenario.

    Current: cold, dirty, off
    Target:  hot, dirty, on   (only temperature + calibration change)

    RAG: WARMUP(30) → CALIBRATE(15)  — strictly sequential
    Expected makespan: 45 min
    """
    session.add(MachineState(id=1, machine_id=1, state_type="current",
                             label="Cold Standby"))
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
                             label="Hot Calibrated"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=2, feature_key="temperature_level",
                            feature_value="hot"),
        MachineStateFeature(machine_state_id=2, feature_key="clean_level",
                            feature_value="dirty"),   # unchanged → no delta
        MachineStateFeature(machine_state_id=2, feature_key="calibration",
                            feature_value="on"),
    ])

    await session.commit()


async def seed_parallel_states(session: AsyncSession) -> None:
    """
    States for parallel scenario.

    Current: cold, dirty, off
    Target:  hot, clean, on   (all 3 features change)

    RAG: WARMUP(30) ──→ CALIBRATE(15)
         CLEANING(20) ─/  (independent, parallel with WARMUP)

    Expected makespan: 45 min  (30 + 15; CLEANING fits within WARMUP window)
    Serial total would be: 65 min (30 + 20 + 15)
    """
    session.add(MachineState(id=1, machine_id=1, state_type="current",
                             label="Cold Standby"))
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

    await session.commit()


# ============================================================
# Composite seed fixtures
# ============================================================


@pytest_asyncio.fixture
async def serial_scenario(db_session):
    """Seed everything for serial test scenario."""
    await seed_base_data(db_session)
    await seed_op_rules(db_session)
    await seed_serial_states(db_session)


@pytest_asyncio.fixture
async def parallel_scenario(db_session):
    """Seed everything for parallel test scenario."""
    await seed_base_data(db_session)
    await seed_op_rules(db_session)
    await seed_parallel_states(db_session)
