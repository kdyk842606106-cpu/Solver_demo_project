"""
Objective registry for CP-SAT optimization goals.

Provides Objective implementations via decorator registration.
Supports weighted CP-SAT objective expressions.
"""

from abc import ABC, abstractmethod
from typing import Any, ClassVar

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
    def build_expression(self, model: ScheduleModel, config: dict[str, Any] | None = None) -> Any:
        """Build a CP-SAT linear expression for this objective."""
        ...

    def apply_to_model(self, model: ScheduleModel) -> None:
        """Backward-compatible single-objective apply helper."""
        model.model.minimize(self.build_expression(model, {}))


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

        Build one weighted objective expression. CP-SAT only keeps the last
        minimize() call, so all objective terms must be combined here.
        """
        if not objectives:
            cls.get("minimize_makespan").apply_to_model(model)
            model.objective_cache["metadata"] = [
                {"type": "minimize_makespan", "weight": 1.0, "weight_int": 1000}
            ]
            return

        terms = []
        metadata = []
        for obj_dict in objectives:
            obj_type = obj_dict.get("type")
            if obj_type not in _OBJECTIVES:
                raise KeyError(f"Unknown objective type: {obj_type}")
            weight_int = _weight_to_int(obj_dict.get("weight", 1.0))
            if weight_int <= 0:
                continue
            expression = cls.get(obj_type).build_expression(model, obj_dict)
            terms.append(weight_int * expression)
            metadata.append({
                "type": obj_type,
                "weight": obj_dict.get("weight", 1.0),
                "weight_int": weight_int,
            })

        if not terms:
            terms.append(1000 * model.makespan)
            metadata.append({"type": "minimize_makespan", "weight": 1.0, "weight_int": 1000})
        model.objective_cache["metadata"] = metadata
        model.model.minimize(sum(terms))


def _weight_to_int(weight: Any) -> int:
    try:
        return max(0, int(round(float(weight) * 1000)))
    except (TypeError, ValueError):
        return 1000


def _group_windows(
    model: ScheduleModel,
    *,
    groups: dict[int, list[int]],
    cache_key: str,
    var_prefix: str,
) -> dict[int, dict[str, Any]]:
    cached = model.objective_cache.get(cache_key)
    if cached is not None:
        return cached

    windows: dict[int, dict[str, Any]] = {}
    for group_id, step_orders in sorted(groups.items()):
        starts = [model.task_vars[step_order].start for step_order in step_orders]
        ends = [model.task_vars[step_order].end for step_order in step_orders]
        group_start = model.model.new_int_var(0, model.horizon, f"{var_prefix}_{group_id}_start")
        group_end = model.model.new_int_var(0, model.horizon, f"{var_prefix}_{group_id}_end")
        group_span = model.model.new_int_var(0, model.horizon, f"{var_prefix}_{group_id}_span")
        model.model.add_min_equality(group_start, starts)
        model.model.add_max_equality(group_end, ends)
        model.model.add(group_span == group_end - group_start)
        windows[group_id] = {
            "start": group_start,
            "end": group_end,
            "span": group_span,
            "step_orders": step_orders,
        }
    model.objective_cache[cache_key] = windows
    return windows


def _group_gap_terms(
    model: ScheduleModel,
    *,
    groups: dict[int, list[int]],
    windows_cache_key: str,
    cache_key: str,
    var_prefix: str,
) -> list[Any]:
    cached = model.objective_cache.get(cache_key)
    if cached is not None:
        return cached

    terms = []
    for group_id, window in _group_windows(
        model,
        groups=groups,
        cache_key=windows_cache_key,
        var_prefix=var_prefix,
    ).items():
        duration_sum = sum(model.task_vars[step_order].duration for step_order in window["step_orders"])
        gap = model.model.new_int_var(0, model.horizon, f"{var_prefix}_{group_id}_gap")
        model.model.add(gap >= window["span"] - duration_sum)
        terms.append(gap)
    model.objective_cache[cache_key] = terms
    return terms


def _group_interruption_terms(
    model: ScheduleModel,
    *,
    groups: dict[int, list[int]],
    windows_cache_key: str,
    cache_key: str,
    var_prefix: str,
) -> list[Any]:
    cached = model.objective_cache.get(cache_key)
    if cached is not None:
        return cached

    terms = []
    all_step_orders = set(model.task_vars)
    for group_id, window in _group_windows(
        model,
        groups=groups,
        cache_key=windows_cache_key,
        var_prefix=var_prefix,
    ).items():
        group_steps = set(window["step_orders"])
        outside_steps = sorted(all_step_orders - group_steps)
        for outside_step in outside_steps:
            tv = model.task_vars[outside_step]
            starts_inside = model.model.new_bool_var(
                f"{var_prefix}_{group_id}_outside_{outside_step}_starts_inside"
            )
            ends_inside = model.model.new_bool_var(
                f"{var_prefix}_{group_id}_outside_{outside_step}_ends_inside"
            )
            interruption = model.model.new_bool_var(
                f"{var_prefix}_{group_id}_outside_{outside_step}_interrupts"
            )

            model.model.add(tv.start >= window["start"]).only_enforce_if(starts_inside)
            model.model.add(tv.start < window["start"]).only_enforce_if(starts_inside.Not())
            model.model.add(tv.end <= window["end"]).only_enforce_if(ends_inside)
            model.model.add(tv.end > window["end"]).only_enforce_if(ends_inside.Not())

            model.model.add_bool_and([starts_inside, ends_inside]).only_enforce_if(interruption)
            model.model.add_bool_or([starts_inside.Not(), ends_inside.Not(), interruption])
            terms.append(interruption)
    model.objective_cache[cache_key] = terms
    return terms


def _activity_group_windows(model: ScheduleModel) -> dict[int, dict[str, Any]]:
    return _group_windows(
        model,
        groups=model.activity_groups,
        cache_key="activity_group_windows",
        var_prefix="activity_group",
    )


def _activity_group_gap_terms(model: ScheduleModel) -> list[Any]:
    return _group_gap_terms(
        model,
        groups=model.activity_groups,
        windows_cache_key="activity_group_windows",
        cache_key="activity_group_gaps",
        var_prefix="activity_group",
    )


def _activity_group_interruption_terms(model: ScheduleModel) -> list[Any]:
    return _group_interruption_terms(
        model,
        groups=model.activity_groups,
        windows_cache_key="activity_group_windows",
        cache_key="activity_group_interruptions",
        var_prefix="activity_group",
    )


def _state_group_windows(model: ScheduleModel) -> dict[int, dict[str, Any]]:
    return _group_windows(
        model,
        groups=model.state_groups,
        cache_key="state_group_windows",
        var_prefix="state_group",
    )


def _state_group_gap_terms(model: ScheduleModel) -> list[Any]:
    return _group_gap_terms(
        model,
        groups=model.state_groups,
        windows_cache_key="state_group_windows",
        cache_key="state_group_gaps",
        var_prefix="state_group",
    )


def _state_group_interruption_terms(model: ScheduleModel) -> list[Any]:
    return _group_interruption_terms(
        model,
        groups=model.state_groups,
        windows_cache_key="state_group_windows",
        cache_key="state_group_interruptions",
        var_prefix="state_group",
    )


@register_objective("minimize_makespan")
class MinimizeMakespanObjective(Objective):
    @property
    def objective_type(self) -> str:
        return "minimize_makespan"

    def build_expression(self, model: ScheduleModel, config: dict[str, Any] | None = None) -> Any:
        return model.makespan


@register_objective("minimize_activity_group_span")
class MinimizeActivityGroupSpanObjective(Objective):
    @property
    def objective_type(self) -> str:
        return "minimize_activity_group_span"

    def build_expression(self, model: ScheduleModel, config: dict[str, Any] | None = None) -> Any:
        return sum(window["span"] for window in _activity_group_windows(model).values())


@register_objective("minimize_activity_group_gaps")
class MinimizeActivityGroupGapsObjective(Objective):
    @property
    def objective_type(self) -> str:
        return "minimize_activity_group_gaps"

    def build_expression(self, model: ScheduleModel, config: dict[str, Any] | None = None) -> Any:
        return sum(_activity_group_gap_terms(model))


@register_objective("minimize_activity_group_interruptions")
class MinimizeActivityGroupInterruptionsObjective(Objective):
    @property
    def objective_type(self) -> str:
        return "minimize_activity_group_interruptions"

    def build_expression(self, model: ScheduleModel, config: dict[str, Any] | None = None) -> Any:
        return sum(_activity_group_interruption_terms(model))


@register_objective("minimize_state_group_span")
class MinimizeStateGroupSpanObjective(Objective):
    @property
    def objective_type(self) -> str:
        return "minimize_state_group_span"

    def build_expression(self, model: ScheduleModel, config: dict[str, Any] | None = None) -> Any:
        return sum(window["span"] for window in _state_group_windows(model).values())


@register_objective("minimize_state_group_gaps")
class MinimizeStateGroupGapsObjective(Objective):
    @property
    def objective_type(self) -> str:
        return "minimize_state_group_gaps"

    def build_expression(self, model: ScheduleModel, config: dict[str, Any] | None = None) -> Any:
        return sum(_state_group_gap_terms(model))


@register_objective("minimize_state_group_interruptions")
class MinimizeStateGroupInterruptionsObjective(Objective):
    @property
    def objective_type(self) -> str:
        return "minimize_state_group_interruptions"

    def build_expression(self, model: ScheduleModel, config: dict[str, Any] | None = None) -> Any:
        return sum(_state_group_interruption_terms(model))
