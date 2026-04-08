"""
Unit tests for Pydantic schemas.

Tests cover:
- Schema validation
- Field constraints
- Model conversion
"""

import pytest
from pydantic import ValidationError

from app.db.schemas import (
    MachineCreate,
    MachineResponse,
    MachineStateCreate,
    MachineTypeCreate,
    OpRuleCreate,
    OpRuleEffectCreate,
    OpRulePrecondCreate,
    ResourceCreate,
    SolveRequestCreate,
)


class TestMachineTypeSchemas:
    """Tests for MachineType schemas."""

    def test_machine_type_create_valid(self):
        """Test valid machine type creation."""
        data = {
            "code": "CNC_LATHE",
            "name": "CNC Lathe",
            "description": "A CNC lathe machine",
        }
        schema = MachineTypeCreate(**data)
        assert schema.code == "CNC_LATHE"
        assert schema.name == "CNC Lathe"
        assert schema.description == "A CNC lathe machine"

    def test_machine_type_create_minimal(self):
        """Test machine type creation with minimal fields."""
        data = {"code": "MILL", "name": "Mill"}
        schema = MachineTypeCreate(**data)
        assert schema.code == "MILL"
        assert schema.name == "Mill"
        assert schema.description is None

    def test_machine_type_create_invalid_code_too_long(self):
        """Test that code exceeding max length fails."""
        data = {"code": "A" * 100, "name": "Test"}
        with pytest.raises(ValidationError):
            MachineTypeCreate(**data)


class TestMachineSchemas:
    """Tests for Machine schemas."""

    def test_machine_create_valid(self):
        """Test valid machine creation."""
        data = {
            "machine_type_id": 1,
            "code": "M-001",
            "name": "Main Lathe",
            "location": "Workshop A",
        }
        schema = MachineCreate(**data)
        assert schema.machine_type_id == 1
        assert schema.code == "M-001"
        assert schema.location == "Workshop A"

    def test_machine_create_invalid_machine_type_id(self):
        """Test that machine_type_id must be positive."""
        data = {"machine_type_id": 0, "code": "M-001", "name": "Test"}
        with pytest.raises(ValidationError):
            MachineCreate(**data)


class TestMachineStateSchemas:
    """Tests for MachineState schemas."""

    def test_machine_state_create_with_features(self):
        """Test machine state creation with features."""
        data = {
            "machine_id": 1,
            "state_type": "current",
            "label": "Cold Standby",
            "features": {
                "temperature_level": "cold",
                "clean_level": "dirty",
            },
        }
        schema = MachineStateCreate(**data)
        assert schema.machine_id == 1
        assert schema.state_type == "current"
        assert schema.features["temperature_level"] == "cold"

    def test_machine_state_create_empty_features(self):
        """Test machine state creation with empty features."""
        data = {
            "machine_id": 1,
            "state_type": "target",
            "features": {},
        }
        schema = MachineStateCreate(**data)
        assert schema.features == {}


class TestOpRuleSchemas:
    """Tests for OpRule schemas."""

    def test_op_rule_create_with_precond_and_effect(self):
        """Test operation rule creation with preconditions and effects."""
        data = {
            "machine_type_id": 1,
            "code": "OP_WARMUP",
            "name": "Warm Up",
            "duration_min": 30,
            "preconditions": [
                {
                    "feature_key": "temperature_level",
                    "operator": "eq",
                    "feature_value": "cold",
                }
            ],
            "effects": [
                {
                    "feature_key": "temperature_level",
                    "new_value": "hot",
                }
            ],
        }
        schema = OpRuleCreate(**data)
        assert schema.code == "OP_WARMUP"
        assert len(schema.preconditions) == 1
        assert schema.preconditions[0].feature_key == "temperature_level"
        assert len(schema.effects) == 1
        assert schema.effects[0].new_value == "hot"

    def test_op_rule_create_invalid_duration(self):
        """Test that duration must be at least 1."""
        data = {
            "machine_type_id": 1,
            "code": "OP_TEST",
            "name": "Test",
            "duration_min": 0,
        }
        with pytest.raises(ValidationError):
            OpRuleCreate(**data)


class TestResourceSchemas:
    """Tests for Resource schemas."""

    def test_resource_create_valid(self):
        """Test valid resource creation."""
        data = {
            "code": "TECH-01",
            "name": "Technician John",
            "resource_type": "TECHNICIAN",
            "capacity": 1,
            "is_available": True,
            "meta": {"skills": ["lathe"]},
        }
        schema = ResourceCreate(**data)
        assert schema.code == "TECH-01"
        assert schema.capacity == 1
        assert schema.meta["skills"] == ["lathe"]

    def test_resource_create_invalid_capacity(self):
        """Test that capacity must be at least 1."""
        data = {
            "code": "TECH-01",
            "name": "Test",
            "resource_type": "TECHNICIAN",
            "capacity": 0,
        }
        with pytest.raises(ValidationError):
            ResourceCreate(**data)


class TestSolveRequestSchemas:
    """Tests for SolveRequest schemas."""

    def test_solve_request_create_valid(self):
        """Test valid solve request creation."""
        data = {
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
            "objective": "minimize_makespan",
        }
        schema = SolveRequestCreate(**data)
        assert schema.machine_id == 1
        assert schema.current_state_id == 1
        assert schema.target_state_id == 2
        assert schema.objective == "minimize_makespan"

    def test_solve_request_create_default_objective(self):
        """Test that objective defaults to minimize_makespan."""
        data = {
            "machine_id": 1,
            "current_state_id": 1,
            "target_state_id": 2,
        }
        schema = SolveRequestCreate(**data)
        assert schema.objective == "minimize_makespan"
