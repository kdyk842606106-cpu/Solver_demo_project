"""Optional plan-adjustment constraints and stability objectives.

The Scheduler only consumes normalized step-order based data.  UI selection
geometry and database step ids are resolved by the application service before
this module is called.
"""

from typing import Any


PRIORITY_WEIGHTS = {"high": 4, "normal": 2, "low": 1}


def adjustment_horizon_floor(context: dict[str, Any] | None) -> int:
    """Return a safe lower bound for the model horizon."""
    if not context:
        return 0
    values = [int(value) for value in (context.get("base_starts") or {}).values()]
    for item in context.get("constraints") or []:
        value = item.get("value_min")
        if value is not None:
            values.append(int(value))
    return max(values, default=0)


def apply_adjustment_constraints(
    schedule_model: Any,
    context: dict[str, Any] | None,
) -> None:
    """Compile canonical adjustment constraints with assumption literals."""
    if not context:
        return
    assumption_map: dict[int, dict[str, Any]] = {}
    base_starts = {
        int(step_order): int(value)
        for step_order, value in (context.get("base_starts") or {}).items()
    }
    for index, item in enumerate(context.get("constraints") or []):
        constraint_type = item.get("type")
        if constraint_type == "priority":
            continue
        constraint_id = str(item.get("id") or f"constraint-{index + 1}")
        literal = schedule_model.model.new_bool_var(f"adjustment_assumption_{index + 1}")
        schedule_model.model.add_assumption(literal)
        assumption_map[literal.index] = {
            "constraint_id": constraint_id,
            "type": constraint_type,
            "step_orders": list(item.get("step_orders") or []),
            "predecessor_step_order": item.get("predecessor_step_order"),
            "successor_step_order": item.get("successor_step_order"),
        }
        if constraint_type in {"not_before", "finish_not_after", "fixed_start"}:
            value_min = int(item["value_min"])
            for step_order in item.get("step_orders") or []:
                task = schedule_model.task_vars[int(step_order)]
                if constraint_type == "not_before":
                    schedule_model.model.add(task.start >= value_min).only_enforce_if(literal)
                elif constraint_type == "finish_not_after":
                    schedule_model.model.add(task.end <= value_min).only_enforce_if(literal)
                else:
                    schedule_model.model.add(task.start == value_min).only_enforce_if(literal)
        elif constraint_type == "freeze":
            for step_order in item.get("step_orders") or []:
                step_order = int(step_order)
                schedule_model.model.add(
                    schedule_model.task_vars[step_order].start == base_starts[step_order]
                ).only_enforce_if(literal)
        elif constraint_type == "precedence":
            predecessor = int(item["predecessor_step_order"])
            successor = int(item["successor_step_order"])
            schedule_model.model.add(
                schedule_model.task_vars[successor].start
                >= schedule_model.task_vars[predecessor].end
            ).only_enforce_if(literal)
    schedule_model.adjustment_assumption_map = assumption_map


def build_stability_stages(
    schedule_model: Any,
    context: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Build the locked lexicographic stability expressions."""
    if not context:
        return []
    model = schedule_model.model
    base_starts = {
        int(step_order): int(value)
        for step_order, value in (context.get("base_starts") or {}).items()
    }
    scope = {int(value) for value in context.get("scope_step_orders") or []}
    priority_by_step = {
        int(step_order): str(value)
        for step_order, value in (context.get("priority_by_step") or {}).items()
    }
    changed: dict[int, Any] = {}
    displacement: dict[int, Any] = {}
    for step_order, task in schedule_model.task_vars.items():
        if step_order not in base_starts:
            continue
        delta = model.new_int_var(0, schedule_model.horizon, f"adjustment_delta_{step_order}")
        moved = model.new_bool_var(f"adjustment_changed_{step_order}")
        model.add_abs_equality(delta, task.start - base_starts[step_order])
        model.add(delta == 0).only_enforce_if(moved.Not())
        model.add(delta >= 1).only_enforce_if(moved)
        displacement[step_order] = delta
        changed[step_order] = moved

    outside = sorted(set(changed) - scope)
    all_steps = sorted(changed)
    priority_expression = sum(
        PRIORITY_WEIGHTS.get(priority_by_step.get(step_order, "normal"), 2)
        * schedule_model.task_vars[step_order].start
        for step_order in all_steps
    )
    return [
        {"type": "minimize_outside_changed_count", "expression": sum(changed[s] for s in outside)},
        {"type": "minimize_outside_displacement", "expression": sum(displacement[s] for s in outside)},
        {"type": "minimize_all_changed_count", "expression": sum(changed[s] for s in all_steps)},
        {"type": "minimize_all_displacement", "expression": sum(displacement[s] for s in all_steps)},
        {"type": "minimize_priority_weighted_start", "expression": priority_expression},
    ]


def infeasible_constraint_core(solver: Any, schedule_model: Any) -> list[dict[str, Any]]:
    """Translate a CP-SAT sufficient assumption core into stable diagnostics."""
    mapping = getattr(schedule_model, "adjustment_assumption_map", {}) or {}
    result = []
    for literal_index in solver.sufficient_assumptions_for_infeasibility():
        item = mapping.get(abs(int(literal_index)))
        if item and item not in result:
            result.append(item)
    return result
