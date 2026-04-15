"""
Unit tests for OperatorRegistry and all 7 Operator implementations.

Covers: eq, neq, gt, gte, lt, lte, in
"""

import pytest
from app.core.solver.operators import (
    OperatorRegistry,
    EqOperator,
    NeqOperator,
    GtOperator,
    GteOperator,
    LtOperator,
    LteOperator,
    InOperator,
)


class TestEqOperator:
    def test_eq_string_match(self):
        op = EqOperator()
        assert op.evaluate("hot", "hot", None) is True

    def test_eq_string_no_match(self):
        op = EqOperator()
        assert op.evaluate("hot", "cold", None) is False

    def test_eq_registry(self):
        assert OperatorRegistry.get("eq") is not None
        assert OperatorRegistry.evaluate_precond("a", "eq", "a", None) is True
        assert OperatorRegistry.evaluate_precond("a", "eq", "b", None) is False


class TestNeqOperator:
    def test_neq_match(self):
        op = NeqOperator()
        assert op.evaluate("hot", "cold", None) is True

    def test_neq_no_match(self):
        op = NeqOperator()
        assert op.evaluate("hot", "hot", None) is False

    def test_neq_registry(self):
        assert OperatorRegistry.evaluate_precond("a", "neq", "b", None) is True
        assert OperatorRegistry.evaluate_precond("a", "neq", "a", None) is False


class TestGtOperator:
    def test_gt_greater(self):
        op = GtOperator()
        assert op.evaluate("10", "5", None) is True

    def test_gt_equal(self):
        op = GtOperator()
        assert op.evaluate("5", "5", None) is False

    def test_gt_less(self):
        op = GtOperator()
        assert op.evaluate("3", "5", None) is False

    def test_gt_non_numeric_returns_false(self):
        op = GtOperator()
        assert op.evaluate("hot", "cold", None) is False

    def test_gt_decimal(self):
        op = GtOperator()
        assert op.evaluate("3.5", "3.0", None) is True
        assert op.evaluate("3.0", "3.0", None) is False


class TestGteOperator:
    def test_gte_greater(self):
        op = GteOperator()
        assert op.evaluate("10", "5", None) is True

    def test_gte_equal(self):
        op = GteOperator()
        assert op.evaluate("5", "5", None) is True

    def test_gte_less(self):
        op = GteOperator()
        assert op.evaluate("3", "5", None) is False

    def test_gte_non_numeric_returns_false(self):
        op = GteOperator()
        assert op.evaluate("hot", "cold", None) is False

    def test_gte_decimal(self):
        op = GteOperator()
        assert op.evaluate("3.0", "3.0", None) is True
        assert op.evaluate("2.9", "3.0", None) is False


class TestLtOperator:
    def test_lt_less(self):
        op = LtOperator()
        assert op.evaluate("3", "5", None) is True

    def test_lt_equal(self):
        op = LtOperator()
        assert op.evaluate("5", "5", None) is False

    def test_lt_greater(self):
        op = LtOperator()
        assert op.evaluate("10", "5", None) is False

    def test_lt_non_numeric_returns_false(self):
        op = LtOperator()
        assert op.evaluate("hot", "cold", None) is False

    def test_lt_decimal(self):
        op = LtOperator()
        assert op.evaluate("2.9", "3.0", None) is True


class TestLteOperator:
    def test_lte_less(self):
        op = LteOperator()
        assert op.evaluate("3", "5", None) is True

    def test_lte_equal(self):
        op = LteOperator()
        assert op.evaluate("5", "5", None) is True

    def test_lte_greater(self):
        op = LteOperator()
        assert op.evaluate("10", "5", None) is False

    def test_lte_non_numeric_returns_false(self):
        op = LteOperator()
        assert op.evaluate("hot", "cold", None) is False

    def test_lte_decimal(self):
        op = LteOperator()
        assert op.evaluate("3.0", "3.0", None) is True
        assert op.evaluate("3.1", "3.0", None) is False


class TestInOperator:
    def test_in_value_list_match(self):
        op = InOperator()
        assert op.evaluate("a", "", ["a", "b", "c"]) is True

    def test_in_value_list_no_match(self):
        op = InOperator()
        assert op.evaluate("d", "", ["a", "b", "c"]) is False

    def test_in_value_list_empty(self):
        op = InOperator()
        assert op.evaluate("a", "", []) is False

    def test_in_comma_separated_fallback(self):
        op = InOperator()
        assert op.evaluate("b", "a, b, c", None) is True
        assert op.evaluate("d", "a, b, c", None) is False

    def test_in_registry(self):
        assert OperatorRegistry.evaluate_precond("b", "in", "a,b,c", None) is True
        assert OperatorRegistry.evaluate_precond("z", "in", "a,b,c", None) is False
        assert OperatorRegistry.evaluate_precond("b", "in", "a,b,c", ["b", "d"]) is True

    def test_in_priority_value_list_over_feature_value(self):
        assert OperatorRegistry.evaluate_precond("z", "in", "x,y,z", ["a", "b"]) is False
        assert OperatorRegistry.evaluate_precond("a", "in", "x,y,z", ["a", "b"]) is True


class TestOperatorRegistryUnknown:
    def test_unknown_operator_raises_key_error(self):
        with pytest.raises(KeyError):
            OperatorRegistry.get("unknown")

    def test_evaluate_unknown_raises_key_error(self):
        with pytest.raises(KeyError):
            OperatorRegistry.evaluate_precond("a", "unknown", "a", None)
