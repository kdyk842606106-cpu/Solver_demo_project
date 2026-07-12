"""Unit tests for Phase 1 numeric planner helpers."""

from app.core.planner.numeric import (
    NUMERIC_EXACT_TARGET_UNREACHABLE,
    NUMERIC_IMPLICIT_GOAL_CYCLE,
    NUMERIC_INVALID_VALUE,
    NUMERIC_MAX_STEPS_EXCEEDED,
    NUMERIC_NO_PROVIDER,
    plan_exact_numeric_feature,
)


class MockEffect:
    def __init__(self, feature_key, effect_type, new_value=None, delta_value=None):
        self.feature_key = feature_key
        self.effect_type = effect_type
        self.new_value = new_value
        self.delta_value = delta_value


class MockRule:
    def __init__(self, code, duration_min, effects, preconditions=None):
        self.id = hash((code, duration_min, len(effects)))
        self.code = code
        self.duration_min = duration_min
        self.effects = effects
        self.preconditions = preconditions or []


class MockPrecond:
    def __init__(self, feature_key, operator, feature_value):
        self.feature_key = feature_key
        self.operator = operator
        self.feature_value = feature_value


class TestPlanExactNumericFeature:
    def test_repeats_same_rule_multiple_times(self):
        rule = MockRule(
            "OP_FILL_WATER",
            10,
            [MockEffect("water_level", "increment", delta_value=20.0)],
        )

        result = plan_exact_numeric_feature(
            feature_key="water_level",
            current_state={"water_level": "0"},
            target_value="80",
            rules=[rule],
        )

        assert result.status == "success"
        assert len(result.steps) == 4
        assert [step.op_rule.code for step in result.steps] == [
            "OP_FILL_WATER",
            "OP_FILL_WATER",
            "OP_FILL_WATER",
            "OP_FILL_WATER",
        ]
        assert result.steps[0].before_state["water_level"] == "0"
        assert result.steps[-1].after_state["water_level"] == "80"
        assert result.steps[1].predecessor_instance_ids == [result.steps[0].instance_id]

    def test_finds_exact_combination_without_greedy_lock_in(self):
        plus_twenty = MockRule(
            "OP_PLUS_20",
            10,
            [MockEffect("water_level", "increment", delta_value=20.0)],
        )
        plus_ten = MockRule(
            "OP_PLUS_10",
            15,
            [MockEffect("water_level", "increment", delta_value=10.0)],
        )

        result = plan_exact_numeric_feature(
            feature_key="water_level",
            current_state={"water_level": "0"},
            target_value="30",
            rules=[plus_twenty, plus_ten],
        )

        assert result.status == "success"
        assert len(result.steps) == 2
        assert [step.op_rule.code for step in result.steps] == ["OP_PLUS_20", "OP_PLUS_10"]
        assert result.final_state == {"water_level": "30"}

    def test_returns_unreachable_when_exact_value_cannot_be_hit(self):
        plus_twenty = MockRule(
            "OP_PLUS_20",
            10,
            [MockEffect("water_level", "increment", delta_value=20.0)],
        )
        plus_ten = MockRule(
            "OP_PLUS_10",
            15,
            [MockEffect("water_level", "increment", delta_value=10.0)],
        )

        result = plan_exact_numeric_feature(
            feature_key="water_level",
            current_state={"water_level": "0"},
            target_value="25",
            rules=[plus_twenty, plus_ten],
        )

        assert result.status == "no_solution"
        assert result.error_code == NUMERIC_EXACT_TARGET_UNREACHABLE

    def test_supports_reverse_direction(self):
        drain = MockRule(
            "OP_DRAIN_WATER",
            8,
            [MockEffect("water_level", "decrement", delta_value=20.0)],
        )

        result = plan_exact_numeric_feature(
            feature_key="water_level",
            current_state={"water_level": "80"},
            target_value="20",
            rules=[drain],
        )

        assert result.status == "success"
        assert len(result.steps) == 3
        assert result.final_state == {"water_level": "20"}

    def test_filters_direction_mismatch_rules(self):
        drain = MockRule(
            "OP_DRAIN_WATER",
            8,
            [MockEffect("water_level", "decrement", delta_value=20.0)],
        )

        result = plan_exact_numeric_feature(
            feature_key="water_level",
            current_state={"water_level": "0"},
            target_value="40",
            rules=[drain],
        )

        assert result.status == "no_solution"
        assert result.error_code == NUMERIC_NO_PROVIDER

    def test_returns_max_steps_exceeded(self):
        tiny_step = MockRule(
            "OP_PLUS_1",
            1,
            [MockEffect("water_level", "increment", delta_value=1.0)],
        )

        result = plan_exact_numeric_feature(
            feature_key="water_level",
            current_state={"water_level": "0"},
            target_value="1000",
            rules=[tiny_step],
            max_steps=10,
        )

        assert result.status == "error"
        assert result.error_code == NUMERIC_MAX_STEPS_EXCEEDED

    def test_returns_invalid_value_for_non_numeric_input(self):
        rule = MockRule(
            "OP_PLUS_10",
            10,
            [MockEffect("water_level", "increment", delta_value=10.0)],
        )

        result = plan_exact_numeric_feature(
            feature_key="water_level",
            current_state={"water_level": "abc"},
            target_value="20",
            rules=[rule],
        )

        assert result.status == "error"
        assert result.error_code == NUMERIC_INVALID_VALUE

    def test_prefers_fewer_side_effects(self):
        clean_rule = MockRule(
            "OP_FILL_CLEAN",
            12,
            [MockEffect("water_level", "increment", delta_value=20.0)],
        )
        noisy_rule = MockRule(
            "OP_FILL_NOISY",
            5,
            [
                MockEffect("water_level", "increment", delta_value=20.0),
                MockEffect("pressure", "set", new_value="high"),
            ],
        )

        result = plan_exact_numeric_feature(
            feature_key="water_level",
            current_state={"water_level": "0", "pressure": "normal"},
            target_value="20",
            rules=[noisy_rule, clean_rule],
        )

        assert result.status == "success"
        assert result.steps[0].op_rule.code == "OP_FILL_CLEAN"
        assert result.final_state == {"water_level": "20", "pressure": "normal"}

    def test_does_not_mutate_input_state(self):
        rule = MockRule(
            "OP_PLUS_20",
            10,
            [MockEffect("water_level", "increment", delta_value=20.0)],
        )
        state = {"water_level": "0", "pressure": "normal"}

        result = plan_exact_numeric_feature(
            feature_key="water_level",
            current_state=state,
            target_value="20",
            rules=[rule],
        )

        assert result.status == "success"
        assert state == {"water_level": "0", "pressure": "normal"}

    def test_implicit_numeric_precondition_generates_predecessors(self):
        pressurize = MockRule(
            "OP_PRESSURIZE",
            5,
            [MockEffect("pressure", "increment", delta_value=1.0)],
        )
        fill = MockRule(
            "OP_FILL_WATER",
            10,
            [MockEffect("water_level", "increment", delta_value=20.0)],
            preconditions=[MockPrecond("pressure", "gte", "2")],
        )

        result = plan_exact_numeric_feature(
            feature_key="water_level",
            current_state={"water_level": "0", "pressure": "0"},
            target_value="20",
            rules=[fill, pressurize],
        )

        assert result.status == "success"
        assert [step.op_rule.code for step in result.steps] == [
            "OP_PRESSURIZE",
            "OP_PRESSURIZE",
            "OP_FILL_WATER",
        ]
        assert result.steps[-1].predecessor_instance_ids == [result.steps[-2].instance_id]
        assert result.final_state == {"water_level": "20", "pressure": "2"}

    def test_detects_implicit_goal_cycle(self):
        fill = MockRule(
            "OP_FILL_WATER",
            10,
            [MockEffect("water_level", "increment", delta_value=20.0)],
            preconditions=[MockPrecond("pressure", "gte", "2")],
        )
        pressurize = MockRule(
            "OP_PRESSURIZE",
            5,
            [MockEffect("pressure", "increment", delta_value=1.0)],
            preconditions=[MockPrecond("water_level", "gte", "20")],
        )

        result = plan_exact_numeric_feature(
            feature_key="water_level",
            current_state={"water_level": "0", "pressure": "0"},
            target_value="20",
            rules=[fill, pressurize],
        )

        assert result.status == "error"
        assert result.error_code == NUMERIC_IMPLICIT_GOAL_CYCLE
