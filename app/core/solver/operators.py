"""
Operator registry for precondition evaluation.

Provides 7 Operator implementations (eq/neq/gt/gte/lt/lte/in) via decorator registration.
All precondition matching must go through OperatorRegistry - no if/elif dispatch.
"""

from abc import ABC, abstractmethod
from typing import ClassVar


_OPERATORS: dict[str, type["Operator"]] = {}


class Operator(ABC):
    """All comparison operators base class."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Operator name, must match op_rule_precond.operator field value."""
        ...

    @abstractmethod
    def evaluate(
        self,
        current_value: str,
        feature_value: str,
        value_list: list | None,
    ) -> bool:
        """
        Execute comparison.

        Args:
            current_value: Actual feature value in current state (string)
            feature_value: Target value stored in op_rule_precond (string)
            value_list: op_rule_precond.value_list, used when op_type='in'

        Returns:
            bool: True if current value satisfies the operator condition
        """
        ...


def register_operator(name: str):
    """Decorator to register an Operator subclass to the global registry."""
    def decorator(cls: type[Operator]) -> type[Operator]:
        _OPERATORS[name] = cls
        return cls
    return decorator


class OperatorRegistry:
    """Registry for all Operator implementations."""

    _instances: ClassVar[dict[str, Operator]] = {}

    @classmethod
    def get(cls, name: str) -> Operator:
        """Get Operator instance by operator name."""
        if name not in cls._instances:
            if name not in _OPERATORS:
                raise KeyError(f"Unknown operator: {name}")
            cls._instances[name] = _OPERATORS[name]()
        return cls._instances[name]

    @classmethod
    def evaluate_precond(
        cls,
        current_value: str,
        operator_name: str,
        feature_value: str,
        value_list: list | None,
    ) -> bool:
        """Convenience method: get(operator_name).evaluate(...)"""
        return cls.get(operator_name).evaluate(current_value, feature_value, value_list)


@register_operator("eq")
class EqOperator(Operator):
    @property
    def name(self) -> str:
        return "eq"

    def evaluate(
        self,
        current_value: str,
        feature_value: str,
        value_list: list | None,
    ) -> bool:
        return current_value == feature_value


@register_operator("neq")
class NeqOperator(Operator):
    @property
    def name(self) -> str:
        return "neq"

    def evaluate(
        self,
        current_value: str,
        feature_value: str,
        value_list: list | None,
    ) -> bool:
        return current_value != feature_value


@register_operator("gt")
class GtOperator(Operator):
    @property
    def name(self) -> str:
        return "gt"

    def evaluate(
        self,
        current_value: str,
        feature_value: str,
        value_list: list | None,
    ) -> bool:
        try:
            return float(current_value) > float(feature_value)
        except ValueError:
            return False


@register_operator("gte")
class GteOperator(Operator):
    @property
    def name(self) -> str:
        return "gte"

    def evaluate(
        self,
        current_value: str,
        feature_value: str,
        value_list: list | None,
    ) -> bool:
        try:
            return float(current_value) >= float(feature_value)
        except ValueError:
            return False


@register_operator("lt")
class LtOperator(Operator):
    @property
    def name(self) -> str:
        return "lt"

    def evaluate(
        self,
        current_value: str,
        feature_value: str,
        value_list: list | None,
    ) -> bool:
        try:
            return float(current_value) < float(feature_value)
        except ValueError:
            return False


@register_operator("lte")
class LteOperator(Operator):
    @property
    def name(self) -> str:
        return "lte"

    def evaluate(
        self,
        current_value: str,
        feature_value: str,
        value_list: list | None,
    ) -> bool:
        try:
            return float(current_value) <= float(feature_value)
        except ValueError:
            return False


@register_operator("in")
class InOperator(Operator):
    @property
    def name(self) -> str:
        return "in"

    def evaluate(
        self,
        current_value: str,
        feature_value: str,
        value_list: list | None,
    ) -> bool:
        if value_list is not None:
            return current_value in value_list
        allowed = [v.strip() for v in feature_value.split(",")]
        return current_value in allowed
