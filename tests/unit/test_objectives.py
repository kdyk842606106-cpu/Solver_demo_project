"""
Unit tests for ObjectiveRegistry and MinimizeMakespanObjective.

Covers:
- ObjectiveRegistry.get() for known and unknown types
- ObjectiveRegistry.apply_all() with valid, empty, and multiple objectives
- MinimizeMakespanObjective.objective_type and apply_to_model
"""

import pytest
from unittest.mock import MagicMock
from app.core.solver.objectives import (
    MinimizeActivityGroupGapsObjective,
    MinimizeActivityGroupInterruptionsObjective,
    MinimizeActivityGroupSpanObjective,
    ObjectiveRegistry,
    MinimizeMakespanObjective,
)


class TestObjectiveRegistryGet:
    """Test ObjectiveRegistry.get() method."""

    def test_get_minimize_makespan_returns_objective_instance(self):
        """get() with known type returns the correct Objective instance."""
        obj = ObjectiveRegistry.get("minimize_makespan")
        assert isinstance(obj, MinimizeMakespanObjective)

    @pytest.mark.parametrize(
        ("objective_type", "expected_cls"),
        [
            ("minimize_activity_group_span", MinimizeActivityGroupSpanObjective),
            ("minimize_activity_group_gaps", MinimizeActivityGroupGapsObjective),
            ("minimize_activity_group_interruptions", MinimizeActivityGroupInterruptionsObjective),
        ],
    )
    def test_get_activity_group_continuity_objectives(self, objective_type, expected_cls):
        obj = ObjectiveRegistry.get(objective_type)
        assert isinstance(obj, expected_cls)

    def test_get_returns_singleton(self):
        """Multiple get() calls return the same instance."""
        obj1 = ObjectiveRegistry.get("minimize_makespan")
        obj2 = ObjectiveRegistry.get("minimize_makespan")
        assert obj1 is obj2

    def test_get_unknown_raises_key_error(self):
        """get() with unknown type raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            ObjectiveRegistry.get("unknown_objective")
        assert "Unknown objective type" in str(exc_info.value)


class TestMinimizeMakespanObjective:
    """Test MinimizeMakespanObjective class."""

    def test_objective_type_is_minimize_makespan(self):
        """objective_type property returns the correct type string."""
        obj = MinimizeMakespanObjective()
        assert obj.objective_type == "minimize_makespan"

    def test_apply_to_model_calls_minimize_makespan(self):
        """apply_to_model() calls model.model.minimize(model.makespan)."""
        obj = MinimizeMakespanObjective()
        mock_makespan = MagicMock()
        mock_model = MagicMock()
        mock_model.makespan = mock_makespan

        obj.apply_to_model(mock_model)

        mock_model.model.minimize.assert_called_once_with(mock_makespan)


class TestObjectiveRegistryApplyAll:
    """Test ObjectiveRegistry.apply_all() method."""

    def test_apply_all_with_single_objective(self):
        """apply_all() with one objective calls apply_to_model once."""
        mock_model = MagicMock()
        objectives = [{"type": "minimize_makespan", "weight": 1.0}]

        original_get = ObjectiveRegistry.get
        captured_calls = []

        def tracking_get(obj_type):
            result = original_get(obj_type)
            captured_calls.append(result)
            return result

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(ObjectiveRegistry, "get", tracking_get)
            ObjectiveRegistry.apply_all(objectives, mock_model)

        assert len(captured_calls) == 1
        assert isinstance(captured_calls[0], MinimizeMakespanObjective)

    def test_apply_all_with_empty_list_uses_default(self):
        """apply_all() with empty list falls back to minimize_makespan."""
        mock_model = MagicMock()
        original_get = ObjectiveRegistry.get
        called_types = []

        def tracking_get(obj_type):
            called_types.append(obj_type)
            return original_get(obj_type)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(ObjectiveRegistry, "get", tracking_get)
            ObjectiveRegistry.apply_all([], mock_model)

        assert called_types == ["minimize_makespan"]

    def test_apply_all_unknown_type_raises_key_error(self):
        """apply_all() with unknown objective type raises KeyError."""
        mock_model = MagicMock()
        objectives = [{"type": "nonexistent_objective", "weight": 1.0}]

        with pytest.raises(KeyError):
            ObjectiveRegistry.apply_all(objectives, mock_model)
