"""
Unit tests for RuleEvaluator: unified precondition matching and effect application.

Covers: evaluate_precondition, evaluate_preconditions, apply_effect, apply_effects
"""

import pytest
from app.core.solver.operators import OperatorRegistry
from app.core.solver.effects import EffectRegistry
from app.core.solver.rule_evaluator import RuleEvaluator


class MockPrecond:
    def __init__(self, feature_key, operator, feature_value, value_list=None):
        self.feature_key = feature_key
        self.operator = operator
        self.feature_value = feature_value
        self.value_list = value_list


class MockEffect:
    def __init__(self, feature_key, effect_type, new_value=None, delta_value=None):
        self.feature_key = feature_key
        self.effect_type = effect_type
        self.new_value = new_value
        self.delta_value = delta_value


class TestRuleEvaluatorEvaluatePrecondition:
    def test_eq_operator_match(self):
        evaluator = RuleEvaluator()
        precond = MockPrecond("temperature", "eq", "hot")
        state = {"temperature": "hot"}
        assert evaluator.evaluate_precondition(state, precond) is True

    def test_eq_operator_no_match(self):
        evaluator = RuleEvaluator()
        precond = MockPrecond("temperature", "eq", "hot")
        state = {"temperature": "cold"}
        assert evaluator.evaluate_precondition(state, precond) is False

    def test_missing_feature_returns_false(self):
        evaluator = RuleEvaluator()
        precond = MockPrecond("temperature", "eq", "hot")
        state = {"clean": "dirty"}
        assert evaluator.evaluate_precondition(state, precond) is False

    def test_gte_numeric_match(self):
        evaluator = RuleEvaluator()
        precond = MockPrecond("temp", "gte", "50")
        state = {"temp": "75"}
        assert evaluator.evaluate_precondition(state, precond) is True

    def test_gte_numeric_boundary(self):
        evaluator = RuleEvaluator()
        precond = MockPrecond("temp", "gte", "50")
        state = {"temp": "50"}
        assert evaluator.evaluate_precondition(state, precond) is True

    def test_gte_numeric_fail(self):
        evaluator = RuleEvaluator()
        precond = MockPrecond("temp", "gte", "50")
        state = {"temp": "30"}
        assert evaluator.evaluate_precondition(state, precond) is False

    def test_lte_numeric_match(self):
        evaluator = RuleEvaluator()
        precond = MockPrecond("temp", "lte", "30")
        state = {"temp": "20"}
        assert evaluator.evaluate_precondition(state, precond) is True

    def test_lte_numeric_boundary(self):
        evaluator = RuleEvaluator()
        precond = MockPrecond("temp", "lte", "30")
        state = {"temp": "30"}
        assert evaluator.evaluate_precondition(state, precond) is True

    def test_in_value_list(self):
        evaluator = RuleEvaluator()
        precond = MockPrecond("color", "in", "", ["red", "green", "blue"])
        state = {"color": "green"}
        assert evaluator.evaluate_precondition(state, precond) is True

    def test_in_value_list_no_match(self):
        evaluator = RuleEvaluator()
        precond = MockPrecond("color", "in", "", ["red", "green", "blue"])
        state = {"color": "yellow"}
        assert evaluator.evaluate_precondition(state, precond) is False

    def test_in_comma_separated_fallback(self):
        evaluator = RuleEvaluator()
        precond = MockPrecond("size", "in", "S,M,L", None)
        state = {"size": "M"}
        assert evaluator.evaluate_precondition(state, precond) is True

    def test_neq_operator(self):
        evaluator = RuleEvaluator()
        precond = MockPrecond("status", "neq", "off")
        state = {"status": "on"}
        assert evaluator.evaluate_precondition(state, precond) is True


class TestRuleEvaluatorEvaluatePreconditions:
    def test_all_satisfied(self):
        evaluator = RuleEvaluator()
        preconds = [
            MockPrecond("temp", "eq", "hot"),
            MockPrecond("clean", "eq", "clean"),
        ]
        state = {"temp": "hot", "clean": "clean"}
        assert evaluator.evaluate_preconditions(state, preconds) is True

    def test_some_unsatisfied(self):
        evaluator = RuleEvaluator()
        preconds = [
            MockPrecond("temp", "eq", "hot"),
            MockPrecond("clean", "eq", "dirty"),
        ]
        state = {"temp": "hot", "clean": "clean"}
        assert evaluator.evaluate_preconditions(state, preconds) is False

    def test_empty_preconditions(self):
        evaluator = RuleEvaluator()
        state = {"temp": "hot"}
        assert evaluator.evaluate_preconditions(state, []) is True

    def test_missing_feature_one_fails(self):
        evaluator = RuleEvaluator()
        preconds = [
            MockPrecond("temp", "eq", "hot"),
            MockPrecond("pressure", "eq", "normal"),
        ]
        state = {"temp": "hot"}
        assert evaluator.evaluate_preconditions(state, preconds) is False


class TestRuleEvaluatorApplyEffect:
    def test_apply_set_effect(self):
        evaluator = RuleEvaluator()
        effect = MockEffect("temperature", "set", new_value="hot")
        state = {"temperature": "cold"}
        new_state = evaluator.apply_effect(state, effect)
        assert new_state["temperature"] == "hot"
        assert state["temperature"] == "cold"

    def test_apply_set_effect_with_none_current(self):
        evaluator = RuleEvaluator()
        effect = MockEffect("temperature", "set", new_value="hot")
        state = {}
        new_state = evaluator.apply_effect(state, effect)
        assert new_state["temperature"] == "hot"

    def test_apply_increment_effect(self):
        evaluator = RuleEvaluator()
        effect = MockEffect("temp", "increment", delta_value=10.0)
        state = {"temp": "20"}
        new_state = evaluator.apply_effect(state, effect)
        assert new_state["temp"] == "30"

    def test_apply_increment_effect_none_current(self):
        evaluator = RuleEvaluator()
        effect = MockEffect("temp", "increment", delta_value=5.0)
        state = {}
        new_state = evaluator.apply_effect(state, effect)
        assert new_state["temp"] == "5"

    def test_apply_decrement_effect(self):
        evaluator = RuleEvaluator()
        effect = MockEffect("temp", "decrement", delta_value=3.0)
        state = {"temp": "10"}
        new_state = evaluator.apply_effect(state, effect)
        assert new_state["temp"] == "7"

    def test_apply_effect_does_not_mutate_original(self):
        evaluator = RuleEvaluator()
        effect = MockEffect("temperature", "set", new_value="hot")
        state = {"temperature": "cold"}
        new_state = evaluator.apply_effect(state, effect)
        assert state["temperature"] == "cold"
        assert new_state["temperature"] == "hot"


class TestRuleEvaluatorApplyEffects:
    def test_apply_multiple_effects_chain(self):
        evaluator = RuleEvaluator()
        effects = [
            MockEffect("temp", "set", new_value="hot"),
            MockEffect("clean", "set", new_value="clean"),
        ]
        state = {"temp": "cold", "clean": "dirty"}
        new_state = evaluator.apply_effects(state, effects)
        assert new_state["temp"] == "hot"
        assert new_state["clean"] == "clean"

    def test_apply_increment_then_decrement(self):
        evaluator = RuleEvaluator()
        effects = [
            MockEffect("counter", "increment", delta_value=10.0),
            MockEffect("counter", "decrement", delta_value=3.0),
        ]
        state = {"counter": "5"}
        new_state = evaluator.apply_effects(state, effects)
        assert new_state["counter"] == "12"

    def test_apply_effects_empty_list(self):
        evaluator = RuleEvaluator()
        state = {"temp": "hot"}
        new_state = evaluator.apply_effects(state, [])
        assert new_state == state

    def test_apply_effects_preserves_unaffected_features(self):
        evaluator = RuleEvaluator()
        effects = [MockEffect("temp", "set", new_value="hot")]
        state = {"temp": "cold", "color": "red"}
        new_state = evaluator.apply_effects(state, effects)
        assert new_state["temp"] == "hot"
        assert new_state["color"] == "red"
