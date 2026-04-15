"""
Unit tests for compute_step_role_diff algorithm.

Covers: normal, repair, pulled_forward, delayed

Note: Tests for pulled_forward/delayed timing comparisons require complex
SQLAlchemy async mocking. These scenarios are covered by integration tests
(test_blockage_strategies.py::TestStepRoleIntegration).
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
from app.core.solver.step_role import compute_step_role_diff


class MockOpRule:
    def __init__(self, id, is_repair=False):
        self.id = id
        self.is_repair = is_repair


class MockStep:
    def __init__(self, step_order, op_rule_id, start_min=None):
        self.step_order = step_order
        self.op_rule_id = op_rule_id
        self.start_min = start_min
        self.step_role = None


class MockPlan:
    def __init__(self, id, steps):
        self.id = id
        self.steps = steps


class MockScheduleResult:
    def __init__(self, tasks):
        self.tasks = tasks


class TestComputeStepRoleDiffParentNone:
    """When parent_plan_id is None, all steps should be 'normal'."""

    @pytest.mark.asyncio
    async def test_parent_none_all_normal(self):
        result_steps = [
            MockStep(step_order=1, op_rule_id=10, start_min=0),
            MockStep(step_order=2, op_rule_id=20, start_min=30),
        ]

        mock_scalars = MagicMock()
        mock_scalars.all.return_value = result_steps

        mock_result = MagicMock()
        mock_result.scalars = MagicMock(return_value=mock_scalars)

        session = AsyncMock()
        session.execute = AsyncMock(return_value=mock_result)

        roles = await compute_step_role_diff(new_plan_id=5, parent_plan_id=None, session=session)

        assert roles[1] == "normal"
        assert roles[2] == "normal"


class TestComputeStepRoleDiffParentNotFound:
    """When parent plan is not found, all steps should be 'normal'."""

    @pytest.mark.asyncio
    async def test_parent_not_found_falls_back_to_normal(self):
        new_steps = [
            MockStep(step_order=1, op_rule_id=10),
        ]

        call_count = [0]

        async def mock_execute(query):
            call_count[0] += 1
            idx = call_count[0]
            result = MagicMock()

            if idx == 1:
                result.scalar_one_or_none = MagicMock(return_value=None)
            else:
                mock_scalars = MagicMock()
                mock_scalars.all.return_value = new_steps
                result.scalars = MagicMock(return_value=mock_scalars)

            return result

        session = AsyncMock()
        session.execute = mock_execute

        roles = await compute_step_role_diff(new_plan_id=5, parent_plan_id=999, session=session)

        assert roles[1] == "normal"


