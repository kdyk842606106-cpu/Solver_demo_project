"""
Unit tests for EffectRegistry and Effect implementations.

Covers: set, increment, decrement, sub, reset
"""

import pytest
from app.core.solver.effects import (
    EffectRegistry,
    SetEffect,
    IncrementEffect,
    DecrementEffect,
    SubEffect,
    ResetEffect,
)


class TestSetEffect:
    def test_set_with_new_value(self):
        op = SetEffect()
        assert op.apply("cold", "hot", None) == "hot"

    def test_set_with_none_new_value(self):
        op = SetEffect()
        assert op.apply("cold", None, None) == ""

    def test_set_with_none_current_value(self):
        op = SetEffect()
        assert op.apply(None, "warm", None) == "warm"

    def test_set_registry(self):
        assert EffectRegistry.get("set") is not None
        assert EffectRegistry.apply(None, None, "set", None) == ""
        assert EffectRegistry.apply("cold", "hot", "set", None) == "hot"


class TestIncrementEffect:
    def test_increment_basic(self):
        op = IncrementEffect()
        assert op.apply("5", None, 3) == "8"

    def test_increment_none_current(self):
        op = IncrementEffect()
        assert op.apply(None, None, 3) == "3"

    def test_increment_none_delta(self):
        op = IncrementEffect()
        assert op.apply("5", None, None) == "5"

    def test_increment_both_none(self):
        op = IncrementEffect()
        assert op.apply(None, None, None) == "0"

    def test_increment_decimal_max_2_places(self):
        op = IncrementEffect()
        assert op.apply("3.5", None, 0.3) == "3.8"
        assert op.apply("3.5", None, 0.05) == "3.55"
        assert op.apply("3.5", None, 0.555) == "4.05"

    def test_increment_trailing_zero_omitted(self):
        op = IncrementEffect()
        assert op.apply("3.0", None, 2.0) == "5"

    def test_increment_negative_result(self):
        op = IncrementEffect()
        assert op.apply("2", None, 5) == "7"
        assert op.apply("2", None, -5) == "-3"

    def test_increment_non_numeric_current(self):
        op = IncrementEffect()
        assert op.apply("not_a_number", None, 3) == "3"

    def test_increment_registry(self):
        assert EffectRegistry.apply("10", None, "increment", 5) == "15"
        assert EffectRegistry.apply(None, None, "increment", 5) == "5"
        assert EffectRegistry.apply("abc", None, "increment", 5) == "5"


class TestDecrementEffect:
    def test_decrement_basic(self):
        op = DecrementEffect()
        assert op.apply("10", None, 3) == "7"

    def test_decrement_none_current(self):
        op = DecrementEffect()
        assert op.apply(None, None, 3) == "-3"

    def test_decrement_none_delta(self):
        op = DecrementEffect()
        assert op.apply("5", None, None) == "5"

    def test_decrement_both_none(self):
        op = DecrementEffect()
        assert op.apply(None, None, None) == "0"

    def test_decrement_decimal_max_2_places(self):
        op = DecrementEffect()
        assert op.apply("3.5", None, 0.3) == "3.2"
        assert op.apply("3.5", None, 0.05) == "3.45"

    def test_decrement_trailing_zero_omitted(self):
        op = DecrementEffect()
        assert op.apply("5.0", None, 2.0) == "3"

    def test_decrement_negative_result(self):
        op = DecrementEffect()
        assert op.apply("2", None, 5) == "-3"

    def test_decrement_non_numeric_current(self):
        op = DecrementEffect()
        assert op.apply("not_a_number", None, 3) == "-3"

    def test_decrement_registry(self):
        assert EffectRegistry.apply("10", None, "decrement", 3) == "7"
        assert EffectRegistry.apply(None, None, "decrement", 3) == "-3"
        assert EffectRegistry.apply("abc", None, "decrement", 3) == "-3"


class TestSubEffect:
    def test_sub_aliases_decrement_behavior(self):
        op = SubEffect()
        assert op.apply("10", None, 3) == "7"
        assert op.apply(None, None, 3) == "-3"
        assert op.apply("abc", None, 3) == "-3"

    def test_sub_registry(self):
        assert EffectRegistry.apply("10", None, "sub", 3) == "7"


class TestResetEffect:
    def test_reset_with_new_value(self):
        op = ResetEffect()
        assert op.apply("25", "100", None) == "100"

    def test_reset_with_none_new_value(self):
        op = ResetEffect()
        assert op.apply("25", None, None) == ""

    def test_reset_registry(self):
        assert EffectRegistry.apply("25", "100", "reset", None) == "100"


class TestEffectRegistryUnknown:
    def test_unknown_effect_raises_key_error(self):
        with pytest.raises(KeyError):
            EffectRegistry.get("unknown")
