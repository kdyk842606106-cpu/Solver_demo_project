"""
Unit tests for the Planner module.

Tests cover:
- State representation and delta computation
- Operation rule matching
- RAG construction
"""

import pytest
from sqlalchemy import select

from app.core.planner.state import (
    compute_state_delta,
    is_goal,
    freeze,
    unfreeze,
    state_matches_precondition,
    format_state,
)
from app.core.planner.matcher import (
    check_preconditions,
    find_ops_for_delta,
    find_provider,
    get_effect_dict,
    rule_summary,
)
from app.core.planner.executor import (
    apply_effects,
    preview_effects,
    effects_satisfy_precondition,
)
from app.core.planner.search import (
    RAG,
    RAGNode,
    has_cycle,
    find_parallel_groups,
    format_rag,
)
from app.db.models import OpRule, OpRulePrecond, OpRuleEffect


# ============================================================
# State Module Tests
# ============================================================


class TestComputeStateDelta:
    """Tests for compute_state_delta function."""

    def test_empty_states(self):
        """Test delta with empty states."""
        delta = compute_state_delta({}, {})
        assert delta == {}

    def test_identical_states(self):
        """Test delta with identical states."""
        state = {"temperature": "hot", "clean": "clean"}
        delta = compute_state_delta(state, state)
        assert delta == {}

    def test_different_states(self):
        """Test delta with different states."""
        current = {"temperature": "cold", "clean": "dirty", "calibration": "off"}
        target = {"temperature": "hot", "clean": "clean", "calibration": "on"}
        
        delta = compute_state_delta(current, target)
        
        assert len(delta) == 3
        assert delta["temperature"] == ("cold", "hot")
        assert delta["clean"] == ("dirty", "clean")
        assert delta["calibration"] == ("off", "on")

    def test_partial_overlap(self):
        """Test delta with partial overlap."""
        current = {"temperature": "cold", "clean": "clean"}
        target = {"temperature": "hot", "clean": "clean"}
        
        delta = compute_state_delta(current, target)
        
        assert len(delta) == 1
        assert delta["temperature"] == ("cold", "hot")


class TestIsGoal:
    """Tests for is_goal function."""

    def test_is_goal_true(self):
        """Test when current matches target."""
        state = {"temperature": "hot"}
        assert is_goal(state, state) is True

    def test_is_goal_false(self):
        """Test when current doesn't match target."""
        current = {"temperature": "cold"}
        target = {"temperature": "hot"}
        assert is_goal(current, target) is False


class TestFreeze:
    """Tests for freeze and unfreeze functions."""

    def test_freeze_unfreeze(self):
        """Test freeze and unfreeze roundtrip."""
        state = {"temperature": "hot", "clean": "clean"}
        frozen = freeze(state)
        unfrozen = unfreeze(frozen)
        
        assert unfrozen == state

    def test_freeze_is_hashable(self):
        """Test that frozen state is hashable."""
        state = {"temperature": "hot"}
        frozen = freeze(state)
        
        # Should be able to use as dict key
        d = {frozen: "value"}
        assert d[frozen] == "value"


class TestStateMatchesPrecondition:
    """Tests for state_matches_precondition function."""

    def test_eq_operator(self):
        """Test equality operator."""
        state = {"temperature": "hot"}
        assert state_matches_precondition(state, "temperature", "eq", "hot") is True
        assert state_matches_precondition(state, "temperature", "eq", "cold") is False

    def test_neq_operator(self):
        """Test not-equal operator."""
        state = {"temperature": "hot"}
        assert state_matches_precondition(state, "temperature", "neq", "cold") is True
        assert state_matches_precondition(state, "temperature", "neq", "hot") is False

    def test_missing_feature(self):
        """Test with missing feature."""
        state = {"temperature": "hot"}
        assert state_matches_precondition(state, "clean", "eq", "clean") is False


# ============================================================
# Matcher Module Tests
# ============================================================


class TestCheckPreconditions:
    """Tests for check_preconditions function."""

    def test_empty_preconditions(self):
        """Test with no preconditions."""
        state = {"temperature": "hot"}
        assert check_preconditions(state, []) is True

    def test_all_satisfied(self):
        """Test when all preconditions are satisfied."""
        state = {"temperature": "cold", "clean": "dirty"}
        
        # Create mock preconditions
        class MockPrecond:
            def __init__(self, key, op, val):
                self.feature_key = key
                self.operator = op
                self.feature_value = val
        
        preconds = [
            MockPrecond("temperature", "eq", "cold"),
            MockPrecond("clean", "eq", "dirty"),
        ]
        
        assert check_preconditions(state, preconds) is True

    def test_some_unsatisfied(self):
        """Test when some preconditions are not satisfied."""
        state = {"temperature": "cold", "clean": "clean"}
        
        class MockPrecond:
            def __init__(self, key, op, val):
                self.feature_key = key
                self.operator = op
                self.feature_value = val
        
        preconds = [
            MockPrecond("temperature", "eq", "cold"),
            MockPrecond("clean", "eq", "dirty"),  # Not satisfied
        ]
        
        assert check_preconditions(state, preconds) is False


class TestFindOpsForDelta:
    """Tests for find_ops_for_delta function."""

    def test_find_matching_ops(self):
        """Test finding operations that match an effect."""
        class MockEffect:
            def __init__(self, key, val):
                self.feature_key = key
                self.new_value = val
        
        class MockRule:
            def __init__(self, code, effects):
                self.code = code
                self.effects = effects
        
        rules = [
            MockRule("OP_WARMUP", [MockEffect("temperature", "hot")]),
            MockRule("OP_CLEAN", [MockEffect("clean", "clean")]),
        ]
        
        matching = find_ops_for_delta("temperature", "hot", rules)
        
        assert len(matching) == 1
        assert matching[0].code == "OP_WARMUP"

    def test_no_matching_ops(self):
        """Test when no operations match."""
        class MockRule:
            def __init__(self, code, effects):
                self.code = code
                self.effects = effects
        
        rules = [MockRule("OP_TEST", [])]
        
        matching = find_ops_for_delta("temperature", "hot", rules)
        
        assert len(matching) == 0


class TestFindProvider:
    """Tests for find_provider function."""

    def test_find_provider(self):
        """Test finding a provider for a precondition."""
        class MockEffect:
            def __init__(self, key, val):
                self.feature_key = key
                self.new_value = val
        
        class MockRule:
            def __init__(self, code, duration, effects):
                self.id = hash(code)
                self.code = code
                self.duration_min = duration
                self.effects = effects
        
        rules = [
            MockRule("OP_WARMUP", 30, [MockEffect("temperature", "hot")]),
            MockRule("OP_QUICK_WARMUP", 15, [MockEffect("temperature", "hot")]),
        ]
        
        provider = find_provider("temperature", "hot", rules)
        
        # Should select shortest duration
        assert provider.code == "OP_QUICK_WARMUP"
        assert provider.duration_min == 15


# ============================================================
# Executor Module Tests
# ============================================================


class TestApplyEffects:
    """Tests for apply_effects function."""

    def test_apply_single_effect(self):
        """Test applying a single effect."""
        state = {"temperature": "cold"}
        
        class MockEffect:
            def __init__(self, key, val):
                self.feature_key = key
                self.new_value = val
        
        effects = [MockEffect("temperature", "hot")]
        new_state = apply_effects(state, effects)
        
        assert new_state["temperature"] == "hot"
        # Original state should be unchanged
        assert state["temperature"] == "cold"

    def test_apply_multiple_effects(self):
        """Test applying multiple effects."""
        state = {"temperature": "cold", "clean": "dirty"}
        
        class MockEffect:
            def __init__(self, key, val):
                self.feature_key = key
                self.new_value = val
        
        effects = [
            MockEffect("temperature", "hot"),
            MockEffect("clean", "clean"),
        ]
        new_state = apply_effects(state, effects)
        
        assert new_state["temperature"] == "hot"
        assert new_state["clean"] == "clean"


class TestEffectsSatisfyPrecondition:
    """Tests for effects_satisfy_precondition function."""

    def test_satisfies(self):
        """Test when effects satisfy precondition."""
        class MockEffect:
            def __init__(self, key, val):
                self.feature_key = key
                self.new_value = val
        
        effects = [MockEffect("temperature", "hot")]
        
        assert effects_satisfy_precondition(effects, "temperature", "hot") is True
        assert effects_satisfy_precondition(effects, "temperature", "cold") is False


# ============================================================
# RAG Tests
# ============================================================


class TestRAGCycleDetection:
    """Tests for has_cycle function."""

    def test_no_cycle(self):
        """Test RAG without cycle."""
        nodes = [
            RAGNode(id=1, op_rule_id=1, op_rule_code="A", predecessors=[]),
            RAGNode(id=2, op_rule_id=2, op_rule_code="B", predecessors=[1]),
            RAGNode(id=3, op_rule_id=3, op_rule_code="C", predecessors=[2]),
        ]
        edges = [(1, 2), (2, 3)]
        
        assert has_cycle(nodes, edges) is False

    def test_with_cycle(self):
        """Test RAG with cycle."""
        nodes = [
            RAGNode(id=1, op_rule_id=1, op_rule_code="A", predecessors=[3]),
            RAGNode(id=2, op_rule_id=2, op_rule_code="B", predecessors=[1]),
            RAGNode(id=3, op_rule_id=3, op_rule_code="C", predecessors=[2]),
        ]
        edges = [(1, 2), (2, 3), (3, 1)]  # Cycle: 1 -> 2 -> 3 -> 1
        
        assert has_cycle(nodes, edges) is True


class TestFindParallelGroups:
    """Tests for find_parallel_groups function."""

    def test_no_parallel(self):
        """Test RAG with no parallel opportunities."""
        nodes = [
            RAGNode(id=1, op_rule_id=1, op_rule_code="A", predecessors=[]),
            RAGNode(id=2, op_rule_id=2, op_rule_code="B", predecessors=[1]),
        ]
        rag = RAG(nodes=nodes, edges=[(1, 2)])
        
        groups = find_parallel_groups(rag)
        
        assert len(groups) == 0

    def test_with_parallel(self):
        """Test RAG with parallel opportunities."""
        nodes = [
            RAGNode(id=1, op_rule_id=1, op_rule_code="A", predecessors=[]),
            RAGNode(id=2, op_rule_id=2, op_rule_code="B", predecessors=[1]),
            RAGNode(id=3, op_rule_id=3, op_rule_code="C", predecessors=[1]),
        ]
        rag = RAG(nodes=nodes, edges=[(1, 2), (1, 3)])
        
        groups = find_parallel_groups(rag)
        
        # Nodes 2 and 3 have same predecessor (1), so they can run in parallel
        assert len(groups) == 1
        assert groups[0] == [2, 3]

    def test_multiple_parallel_groups(self):
        """Test RAG with multiple parallel groups."""
        nodes = [
            RAGNode(id=1, op_rule_id=1, op_rule_code="A", predecessors=[]),
            RAGNode(id=2, op_rule_id=2, op_rule_code="B", predecessors=[]),
            RAGNode(id=3, op_rule_id=3, op_rule_code="C", predecessors=[1]),
            RAGNode(id=4, op_rule_id=4, op_rule_code="D", predecessors=[1]),
        ]
        rag = RAG(nodes=nodes, edges=[(1, 3), (1, 4)])
        
        groups = find_parallel_groups(rag)
        
        # Nodes 1 and 2 have no predecessors (can run in parallel)
        # Nodes 3 and 4 have same predecessor (can run in parallel)
        assert len(groups) == 2
        assert [1, 2] in groups
        assert [3, 4] in groups
