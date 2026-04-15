"""
Objective registry for CP-SAT optimization goals.

Provides Objective implementations via decorator registration.
Current MVP only implements MinimizeMakespanObjective.
"""

from abc import ABC, abstractmethod
from typing import ClassVar

from app.core.scheduler.model import ScheduleModel


_OBJECTIVES: dict[str, type["Objective"]] = {}


class Objective(ABC):
    """CP-SAT optimization objective base class."""

    @property
    @abstractmethod
    def objective_type(self) -> str:
        """Objective type identifier, must match the type field in objectives array."""
        ...

    @abstractmethod
    def apply_to_model(self, model: ScheduleModel) -> None:
        """Inject this objective into the CP-SAT model."""
        ...


def register_objective(objective_type: str):
    """Decorator to register an Objective subclass to the global registry."""
    def decorator(cls: type[Objective]) -> type[Objective]:
        _OBJECTIVES[objective_type] = cls
        return cls
    return decorator


class ObjectiveRegistry:
    """Registry for all Objective implementations."""

    _instances: ClassVar[dict[str, Objective]] = {}

    @classmethod
    def get(cls, objective_type: str) -> Objective:
        """Get Objective instance by type."""
        if objective_type not in _OBJECTIVES:
            raise KeyError(f"Unknown objective type: {objective_type}")
        if objective_type not in cls._instances:
            cls._instances[objective_type] = _OBJECTIVES[objective_type]()
        return cls._instances[objective_type]

    @classmethod
    def apply_all(
        cls,
        objectives: list[dict],
        model: ScheduleModel,
    ) -> None:
        """
        Apply all objectives from the objectives array to the model.

        MVP: Only minimize_makespan is implemented. Weight field is ignored.
        Multi-objective weighted sum not yet implemented.
        """
        if not objectives:
            cls.get("minimize_makespan").apply_to_model(model)
            return

        for obj_dict in objectives:
            obj_type = obj_dict.get("type")
            if obj_type not in _OBJECTIVES:
                raise KeyError(f"Unknown objective type: {obj_type}")
            cls.get(obj_type).apply_to_model(model)


@register_objective("minimize_makespan")
class MinimizeMakespanObjective(Objective):
    @property
    def objective_type(self) -> str:
        return "minimize_makespan"

    def apply_to_model(self, model: ScheduleModel) -> None:
        model.model.minimize(model.makespan)
