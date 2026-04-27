"""
Effect registry for state transitions.

Provides 3 Effect implementations (set/increment/decrement) via decorator registration.
All effect application must go through EffectRegistry - no if/elif dispatch.
"""

from abc import ABC, abstractmethod
from typing import ClassVar


_EFFECTS: dict[str, type["Effect"]] = {}


def _round_to_max_2_decimal(value: float) -> str:
    """Round to max 2 decimal places, trailing zeros omitted."""
    if value == int(value):
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


class Effect(ABC):
    """All state transition effect types base class."""

    @property
    @abstractmethod
    def effect_type(self) -> str:
        """Effect type name, must match op_rule_effect.effect_type field value."""
        ...

    @abstractmethod
    def apply(
        self,
        current_value: str | None,
        new_value: str | None,
        delta_value: float | None,
    ) -> str:
        """
        Compute new state value after applying effect.

        Args:
            current_value: Current value of the feature in state, None if not set
            new_value: Target value to set (for 'set' effect type, this is the result;
                       for increment/decrement, pass None)
            delta_value: op_rule_effect.delta_value (only used for increment/decrement)

        Returns:
            str: New feature value (统一返回字符串)
        """
        ...


def register_effect(effect_type: str):
    """Decorator to register an Effect subclass to the global registry."""
    def decorator(cls: type[Effect]) -> type[Effect]:
        _EFFECTS[effect_type] = cls
        return cls
    return decorator


class EffectRegistry:
    """Registry for all Effect implementations."""

    _instances: ClassVar[dict[str, Effect]] = {}

    @classmethod
    def get(cls, effect_type: str) -> Effect:
        """Get Effect instance by effect type."""
        if effect_type not in _EFFECTS:
            raise KeyError(f"Unknown effect type: {effect_type}")
        if effect_type not in cls._instances:
            cls._instances[effect_type] = _EFFECTS[effect_type]()
        return cls._instances[effect_type]

    @classmethod
    def apply(
        cls,
        current_value: str | None,
        new_value: str | None,
        effect_type: str,
        delta_value: float | None,
    ) -> str:
        """Convenience method: get(effect_type).apply(current_value, new_value, delta_value)"""
        return cls.get(effect_type).apply(current_value, new_value, delta_value)


@register_effect("set")
class SetEffect(Effect):
    @property
    def effect_type(self) -> str:
        return "set"

    def apply(
        self,
        current_value: str | None,
        new_value: str | None,
        delta_value: float | None,
    ) -> str:
        return new_value if new_value is not None else ""


@register_effect("increment")
class IncrementEffect(Effect):
    @property
    def effect_type(self) -> str:
        return "increment"

    def apply(
        self,
        current_value: str | None,
        new_value: str | None,
        delta_value: float | None,
    ) -> str:
        try:
            base = float(current_value) if current_value else 0.0
        except ValueError:
            base = 0.0
        delta = float(delta_value) if delta_value is not None else 0.0
        return _round_to_max_2_decimal(base + delta)


@register_effect("decrement")
class DecrementEffect(Effect):
    @property
    def effect_type(self) -> str:
        return "decrement"

    def apply(
        self,
        current_value: str | None,
        new_value: str | None,
        delta_value: float | None,
    ) -> str:
        try:
            base = float(current_value) if current_value else 0.0
        except ValueError:
            base = 0.0
        delta = float(delta_value) if delta_value is not None else 0.0
        return _round_to_max_2_decimal(base - delta)
