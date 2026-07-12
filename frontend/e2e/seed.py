"""Seed SQLite DB for Playwright E2E tests."""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
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
from app.db.session import patch_sqlite_types

patch_sqlite_types(force=True)

DB_PATH = Path(__file__).with_name('test.db')
ASYNC_URL = f"sqlite+aiosqlite:///{DB_PATH}"


async def seed_base_data(session):
    """Seed base machine type, feature defs, machine, resources."""
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


async def seed_op_rules(session):
    """Seed operation rules with preconditions, effects, resource reqs."""
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


async def seed_parallel_scenario(session):
    """Seed parallel scenario at id=1,2 so auto-select picks these first."""
    session.add(MachineState(id=1, machine_id=1, state_type="current",
                             label="Cold Dirty Standby"))
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
                             label="Hot Clean Calibrated"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=2, feature_key="temperature_level",
                            feature_value="hot"),
        MachineStateFeature(machine_state_id=2, feature_key="clean_level",
                            feature_value="clean"),
        MachineStateFeature(machine_state_id=2, feature_key="calibration",
                            feature_value="on"),
    ])


async def seed_repair_data(session):
    """Seed repair rules and states for blockage Strategy B."""
    session.add(StateFeatureDef(
        id=50, machine_type_id=1, feature_key="blockage_reason",
        feature_name="Blockage Reason", value_type="string"
    ))

    session.add(OpRule(id=50, machine_type_id=1, code="OP_REPAIR_WORN",
                       name="Repair Worn Parts", duration_min=40, is_active=True,
                       is_repair=True))
    session.add(OpRulePrecond(op_rule_id=50, feature_key="blockage_reason",
                              operator="eq", feature_value="mechanical_wear"))
    session.add(OpRuleEffect(op_rule_id=50, feature_key="blockage_reason",
                             new_value=""))
    session.add(OpRuleResourceReq(op_rule_id=50, resource_type="TECHNICIAN",
                                  quantity=1, is_required=True))

    await session.flush()

    session.add(MachineState(id=3, machine_id=1, state_type="current",
                             label="Cold Standby with Blockage"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=3, feature_key="temperature_level",
                            feature_value="cold"),
        MachineStateFeature(machine_state_id=3, feature_key="clean_level",
                            feature_value="dirty"),
        MachineStateFeature(machine_state_id=3, feature_key="calibration",
                            feature_value="off"),
        MachineStateFeature(machine_state_id=3, feature_key="blockage_reason",
                            feature_value="mechanical_wear"),
    ])

    session.add(MachineState(id=4, machine_id=1, state_type="target",
                             label="Ready for Production with Blockage"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=4, feature_key="temperature_level",
                            feature_value="hot"),
        MachineStateFeature(machine_state_id=4, feature_key="clean_level",
                            feature_value="clean"),
        MachineStateFeature(machine_state_id=4, feature_key="calibration",
                            feature_value="on"),
        MachineStateFeature(machine_state_id=4, feature_key="blockage_reason",
                            feature_value=""),
    ])


async def seed_serial_states(session):
    """Seed serial scenario states at id=5,6."""
    session.add(MachineState(id=5, machine_id=1, state_type="current",
                             label="Cold Standby"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=5, feature_key="temperature_level",
                            feature_value="cold"),
        MachineStateFeature(machine_state_id=5, feature_key="clean_level",
                            feature_value="dirty"),
        MachineStateFeature(machine_state_id=5, feature_key="calibration",
                            feature_value="off"),
    ])

    session.add(MachineState(id=6, machine_id=1, state_type="target",
                             label="Hot Calibrated"))
    await session.flush()
    session.add_all([
        MachineStateFeature(machine_state_id=6, feature_key="temperature_level",
                            feature_value="hot"),
        MachineStateFeature(machine_state_id=6, feature_key="clean_level",
                            feature_value="dirty"),
        MachineStateFeature(machine_state_id=6, feature_key="calibration",
                            feature_value="on"),
    ])


async def main():
    engine = create_async_engine(ASYNC_URL, connect_args={"check_same_thread": False})
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with Session() as session:
        await seed_base_data(session)
        await seed_op_rules(session)
        await seed_parallel_scenario(session)
        await seed_repair_data(session)
        await seed_serial_states(session)
        await session.commit()

    print(f"Seeded: {DB_PATH}")


if __name__ == '__main__':
    asyncio.run(main())
