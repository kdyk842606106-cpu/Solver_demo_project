"""
Unit tests for SQLAlchemy ORM models.

Tests cover:
- Model creation and relationships
- CRUD operations
- Foreign key constraints
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
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


class TestMachineType:
    """Tests for MachineType model."""

    async def test_create_machine_type(self, async_session: AsyncSession):
        """Test creating a machine type."""
        machine_type = MachineType(
            code="CNC_LATHE",
            name="CNC Lathe",
            description="Computer Numerical Control Lathe",
        )
        async_session.add(machine_type)
        await async_session.commit()

        result = await async_session.execute(
            select(MachineType).where(MachineType.code == "CNC_LATHE")
        )
        saved = result.scalar_one()

        assert saved.id is not None
        assert saved.code == "CNC_LATHE"
        assert saved.name == "CNC Lathe"
        assert saved.description == "Computer Numerical Control Lathe"
        assert saved.created_at is not None

    async def test_unique_code_constraint(self, async_session: AsyncSession):
        """Test that machine type code must be unique."""
        mt1 = MachineType(code="MILL", name="Mill 1")
        async_session.add(mt1)
        await async_session.commit()

        mt2 = MachineType(code="MILL", name="Mill 2")
        async_session.add(mt2)

        with pytest.raises(Exception):  # IntegrityError
            await async_session.commit()


class TestMachine:
    """Tests for Machine model."""

    async def test_create_machine(self, async_session: AsyncSession):
        """Test creating a machine with machine type relationship."""
        machine_type = MachineType(code="CNC_LATHE", name="CNC Lathe")
        async_session.add(machine_type)
        await async_session.commit()
        await async_session.refresh(machine_type)

        machine = Machine(
            machine_type_id=machine_type.id,
            code="M-001",
            name="Main Lathe",
            location="Workshop A",
        )
        async_session.add(machine)
        await async_session.commit()

        result = await async_session.execute(
            select(Machine).where(Machine.code == "M-001")
        )
        saved = result.scalar_one()

        assert saved.id is not None
        assert saved.machine_type_id == machine_type.id
        assert saved.code == "M-001"
        assert saved.name == "Main Lathe"
        assert saved.location == "Workshop A"

    async def test_machine_type_relationship(self, async_session: AsyncSession):
        """Test machine -> machine_type relationship."""
        machine_type = MachineType(code="CNC_LATHE", name="CNC Lathe")
        async_session.add(machine_type)
        await async_session.commit()
        await async_session.refresh(machine_type)

        machine = Machine(
            machine_type_id=machine_type.id,
            code="M-001",
            name="Main Lathe",
        )
        async_session.add(machine)
        await async_session.commit()
        await async_session.refresh(machine)

        # Access relationship
        assert machine.machine_type is not None
        assert machine.machine_type.code == "CNC_LATHE"


class TestMachineState:
    """Tests for MachineState model."""

    async def test_create_machine_state(self, async_session: AsyncSession):
        """Test creating a machine state with features."""
        machine_type = MachineType(code="CNC_LATHE", name="CNC Lathe")
        async_session.add(machine_type)
        await async_session.commit()
        await async_session.refresh(machine_type)

        machine = Machine(
            machine_type_id=machine_type.id,
            code="M-001",
            name="Main Lathe",
        )
        async_session.add(machine)
        await async_session.commit()
        await async_session.refresh(machine)

        state = MachineState(
            machine_id=machine.id,
            state_type="current",
            label="Cold Standby",
        )
        async_session.add(state)
        await async_session.commit()
        await async_session.refresh(state)

        # Add features
        feature1 = MachineStateFeature(
            machine_state_id=state.id,
            feature_key="temperature_level",
            feature_value="cold",
        )
        feature2 = MachineStateFeature(
            machine_state_id=state.id,
            feature_key="clean_level",
            feature_value="dirty",
        )
        async_session.add_all([feature1, feature2])
        await async_session.commit()

        # Verify
        result = await async_session.execute(
            select(MachineState).where(MachineState.id == state.id).options(selectinload(MachineState.features))
        )
        saved = result.scalar_one()

        assert saved.id is not None
        assert saved.state_type == "current"
        assert saved.label == "Cold Standby"
        assert len(saved.features) == 2

    async def test_state_features_as_dict(self, async_session: AsyncSession):
        """Test converting state features to dictionary."""
        machine_type = MachineType(code="CNC_LATHE", name="CNC Lathe")
        async_session.add(machine_type)
        await async_session.commit()
        await async_session.refresh(machine_type)

        machine = Machine(
            machine_type_id=machine_type.id,
            code="M-001",
            name="Main Lathe",
        )
        async_session.add(machine)
        await async_session.commit()
        await async_session.refresh(machine)

        state = MachineState(
            machine_id=machine.id,
            state_type="current",
            label="Cold Standby",
        )
        async_session.add(state)
        await async_session.commit()
        await async_session.refresh(state)

        feature1 = MachineStateFeature(
            machine_state_id=state.id,
            feature_key="temperature_level",
            feature_value="cold",
        )
        feature2 = MachineStateFeature(
            machine_state_id=state.id,
            feature_key="clean_level",
            feature_value="dirty",
        )
        async_session.add_all([feature1, feature2])
        await async_session.commit()
        await async_session.refresh(state, ["features"])

        # Convert to dict
        features_dict = {f.feature_key: f.feature_value for f in state.features}
        assert features_dict == {"temperature_level": "cold", "clean_level": "dirty"}


class TestOpRule:
    """Tests for OpRule model with preconditions and effects."""

    async def test_create_op_rule_with_precond_and_effect(
        self, async_session: AsyncSession
    ):
        """Test creating an operation rule with preconditions and effects."""
        machine_type = MachineType(code="CNC_LATHE", name="CNC Lathe")
        async_session.add(machine_type)
        await async_session.commit()
        await async_session.refresh(machine_type)

        op_rule = OpRule(
            machine_type_id=machine_type.id,
            code="OP_WARMUP",
            name="Warm Up",
            duration_min=30,
            description="Warm up the machine",
        )
        async_session.add(op_rule)
        await async_session.commit()
        await async_session.refresh(op_rule)

        # Add precondition
        precond = OpRulePrecond(
            op_rule_id=op_rule.id,
            feature_key="temperature_level",
            operator="eq",
            feature_value="cold",
        )
        async_session.add(precond)

        # Add effect
        effect = OpRuleEffect(
            op_rule_id=op_rule.id,
            feature_key="temperature_level",
            new_value="hot",
        )
        async_session.add(effect)

        await async_session.commit()
        await async_session.refresh(op_rule, ["preconditions", "effects"])

        # Verify
        assert len(op_rule.preconditions) == 1
        assert op_rule.preconditions[0].feature_key == "temperature_level"
        assert op_rule.preconditions[0].feature_value == "cold"

        assert len(op_rule.effects) == 1
        assert op_rule.effects[0].feature_key == "temperature_level"
        assert op_rule.effects[0].new_value == "hot"

    async def test_effect_matching_for_rag(self, async_session: AsyncSession):
        """Test finding operations by effect (for RAG construction)."""
        machine_type = MachineType(code="CNC_LATHE", name="CNC Lathe")
        async_session.add(machine_type)
        await async_session.commit()
        await async_session.refresh(machine_type)

        # Create multiple operations
        op1 = OpRule(
            machine_type_id=machine_type.id,
            code="OP_WARMUP",
            name="Warm Up",
            duration_min=30,
        )
        op2 = OpRule(
            machine_type_id=machine_type.id,
            code="OP_QUICK_WARMUP",
            name="Quick Warm Up",
            duration_min=15,
        )
        async_session.add_all([op1, op2])
        await async_session.commit()

        # Both have effect that sets temperature_level to hot
        effect1 = OpRuleEffect(
            op_rule_id=op1.id,
            feature_key="temperature_level",
            new_value="hot",
        )
        effect2 = OpRuleEffect(
            op_rule_id=op2.id,
            feature_key="temperature_level",
            new_value="hot",
        )
        async_session.add_all([effect1, effect2])
        await async_session.commit()

        # Query: find all operations that can set temperature_level to hot
        result = await async_session.execute(
            select(OpRule)
            .join(OpRuleEffect)
            .where(
                OpRuleEffect.feature_key == "temperature_level",
                OpRuleEffect.new_value == "hot",
                OpRule.is_active == True,
            )
        )
        matching_ops = result.scalars().all()

        assert len(matching_ops) == 2
        # Select shortest (for RAG construction)
        best = min(matching_ops, key=lambda op: op.duration_min)
        assert best.code == "OP_QUICK_WARMUP"
        assert best.duration_min == 15


class TestResource:
    """Tests for Resource model."""

    async def test_create_resource(self, async_session: AsyncSession):
        """Test creating a resource."""
        async_session.add(MachineType(id=1, code="CNC_LATHE", name="CNC Lathe"))
        async_session.add(Machine(id=1, machine_type_id=1, code="M-001", name="Main CNC"))
        await async_session.flush()
        resource = Resource(
            machine_id=1,
            code="TECH-01",
            name="Technician John",
            resource_type="TECHNICIAN",
            capacity=1,
            is_available=True,
            meta={"skills": ["lathe", "mill"]},
        )
        async_session.add(resource)
        await async_session.commit()

        result = await async_session.execute(
            select(Resource).where(Resource.code == "TECH-01")
        )
        saved = result.scalar_one()

        assert saved.id is not None
        assert saved.code == "TECH-01"
        assert saved.resource_type == "TECHNICIAN"
        assert saved.capacity == 1
        assert saved.meta["skills"] == ["lathe", "mill"]
