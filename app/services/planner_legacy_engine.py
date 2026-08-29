"""In-memory adapter for the original Pathfinder and CP-SAT Scheduler."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from ortools.sat.python import cp_model

from app.core.planner.partial_order import partial_order_plan
from app.core.scheduler.loader import RagData, ResourceData, StepData
from app.core.scheduler.model import build_model
from app.core.scheduler.schedule_graph import build_schedule_graph, compute_critical_path
from app.core.scheduler.solver import (
    TaskResult,
    _assign_resources,
    _detect_actual_parallel,
)
from app.db.models import OpRule, OpRuleEffect, OpRulePrecond, StateFeatureDef


DEFAULT_OBJECTIVES = [{"type": "minimize_makespan", "weight": 1.0}]


def run_legacy_pipeline(
    scenario: Any,
    budget: Any,
    *,
    source_payload: dict[str, Any],
    run_id: str,
    modules: dict[str, Any],
    objectives: list[dict[str, Any]] | None = None,
) -> Any:
    """Run the original partial-order Pathfinder followed by CP-SAT scheduling."""

    requested_objectives = objectives or DEFAULT_OBJECTIVES
    state_ids = sorted(scenario.state_by_id)
    planning_active = set(scenario.initial_state_ids)
    for event in scenario.external_events:
        planning_active.update(event.add_state_ids)

    current = {
        state_id: "active" if state_id in planning_active else "inactive"
        for state_id in state_ids
    }
    # Planner state IDs are independent boolean facts.  Only explicitly
    # selected goals/forbidden facts belong in the POP target; copying every
    # current fact would incorrectly require transition inputs to be restored.
    target: dict[str, str] = {}
    for state_id in scenario.goal_state_ids:
        target[state_id] = "active"
    for state_id in scenario.forbidden_state_ids:
        target[state_id] = "inactive"

    feature_defs = {
        state_id: StateFeatureDef(
            id=index,
            machine_type_id=0,
            feature_key=state_id,
            feature_name=state_id,
            value_type="enum",
        )
        for index, state_id in enumerate(state_ids, start=1)
    }
    rules, activity_by_rule_id, instance_limits = _build_rules(scenario)
    pop = partial_order_plan(
        current_state=current,
        target_state=target,
        rules=rules,
        feature_defs=feature_defs,
        instance_limits=instance_limits,
    )
    if pop.status != "success":
        return modules["EngineResult"](
            algorithm="LEGACY",
            run_id=run_id,
            seed=None,
            status="EXHAUSTED_EMPTY" if pop.status == "no_solution" else "ERROR",
            stats={"pathfinder": pop.diagnostics},
            diagnosis={
                "error_code": pop.error_code or "LEGACY_PATHFINDER_FAILED",
                "error_message": pop.error_message,
            },
            error=pop.error_message if pop.status == "error" else None,
        )

    simulator = modules["PathSimulator"](scenario)
    if not pop.nodes:
        return _event_only_result(
            simulator,
            modules,
            run_id=run_id,
            pathfinder_diagnostics=pop.diagnostics,
        )

    rule_by_id = {rule.id: rule for rule in rules}
    activity_by_id = scenario.activity_by_id
    rag_data = _build_rag_data(
        scenario,
        pop,
        rule_by_id,
        activity_by_rule_id,
        source_payload,
    )
    resources = [
        ResourceData(
            id=index,
            code=resource.id,
            name=resource.id,
            resource_type=resource.id,
            capacity=resource.capacity,
        )
        for index, resource in enumerate(scenario.resources, start=1)
    ]
    schedule_model = build_model(rag_data, resources, requested_objectives)
    _apply_execution_mode_constraints(schedule_model, rag_data, activity_by_rule_id, activity_by_id, scenario.execution_mode)

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = float(budget.time_limit_seconds)
    status = solver.solve(schedule_model.model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        status_name = solver.status_name(status)
        return modules["EngineResult"](
            algorithm="LEGACY",
            run_id=run_id,
            seed=None,
            status="TIMEOUT_EMPTY" if status == cp_model.UNKNOWN else "EXHAUSTED_EMPTY",
            stats={
                "pathfinder": pop.diagnostics,
                "scheduler": {
                    "status": status_name,
                    "wall_time_seconds": solver.wall_time,
                    "branches": solver.num_branches,
                },
            },
            diagnosis={
                "error_code": "LEGACY_SCHEDULE_INFEASIBLE" if status == cp_model.INFEASIBLE else "LEGACY_SCHEDULE_TIMEOUT",
                "error_message": f"Scheduler returned {status_name}",
            },
        )

    tasks = _extract_tasks(solver, schedule_model, rag_data, resources)
    try:
        state = _replay_schedule(simulator, tasks, activity_by_rule_id, modules["Action"], scenario.execution_mode)
        candidate = simulator.candidate_from_state(
            state,
            algorithm="LEGACY",
            run_id=run_id,
            seed=None,
            discovered_at_seconds=0.0,
            normalize=False,
        )
    except Exception as exc:
        return modules["EngineResult"](
            algorithm="LEGACY",
            run_id=run_id,
            seed=None,
            status="ERROR",
            stats={
                "pathfinder": pop.diagnostics,
                    "scheduler": _scheduler_stats(solver, status, schedule_model, rag_data, tasks, requested_objectives),
            },
            diagnosis={"error_code": "LEGACY_SCHEDULE_REPLAY_FAILED", "error_message": str(exc)},
            error=str(exc),
        )

    return modules["EngineResult"](
        algorithm="LEGACY",
        run_id=run_id,
        seed=None,
        status="OK",
        paths=(candidate,),
        first_solution_seconds=round(float(solver.wall_time), 6),
        stats={
            "pathfinder": pop.diagnostics,
            "scheduler": _scheduler_stats(solver, status, schedule_model, rag_data, tasks, requested_objectives),
        },
    )


def _build_rules(scenario: Any) -> tuple[list[OpRule], dict[int, str], dict[int, int | None]]:
    rules: list[OpRule] = []
    activity_by_rule_id: dict[int, str] = {}
    instance_limits: dict[int, int | None] = {}
    for index, activity in enumerate(scenario.activities, start=1):
        rule = OpRule(
            id=index,
            machine_type_id=0,
            code=activity.id,
            name=activity.name,
            duration_min=activity.duration,
            is_active=True,
            is_repair=False,
        )
        rule.preconditions = [
            OpRulePrecond(
                id=index * 1000 + relation_index,
                op_rule_id=index,
                feature_key=relation.state_id,
                operator="eq",
                feature_value="active",
            )
            for relation_index, relation in enumerate(activity.precondition_bindings, start=1)
        ]
        effects: list[OpRuleEffect] = []
        effect_index = 1
        for state_id in activity.transition_state_ids:
            effects.append(OpRuleEffect(
                id=index * 1000 + effect_index,
                op_rule_id=index,
                feature_key=state_id,
                new_value="inactive",
                effect_type="set",
            ))
            effect_index += 1
        for state_id in activity.output_state_ids:
            effects.append(OpRuleEffect(
                id=index * 1000 + effect_index,
                op_rule_id=index,
                feature_key=state_id,
                new_value="active",
                effect_type="set",
            ))
            effect_index += 1
        rule.effects = effects
        rules.append(rule)
        activity_by_rule_id[index] = activity.id
        instance_limits[index] = activity.max_instances
    return rules, activity_by_rule_id, instance_limits


def _build_rag_data(
    scenario: Any,
    pop: Any,
    rule_by_id: dict[int, OpRule],
    activity_by_rule_id: dict[int, str],
    source_payload: dict[str, Any],
) -> RagData:
    package_groups = _package_group_metadata(source_payload)
    ancestors = _ancestor_steps(pop.edges, [node.id for node in pop.nodes])
    activity_by_id = scenario.activity_by_id
    steps: list[StepData] = []
    for node in pop.nodes:
        activity_id = activity_by_rule_id[node.op_rule_id]
        activity = activity_by_id[activity_id]
        predecessor_outputs = {
            output_state_id
            for predecessor in ancestors.get(node.id, set())
            for output_state_id in activity_by_id[
                activity_by_rule_id[next(item.op_rule_id for item in pop.nodes if item.id == predecessor)]
            ].output_state_ids
        }
        start_windows = _activity_start_windows(scenario, activity, predecessor_outputs)
        earliest_window_start = min((start for start, _ in start_windows), default=0)
        event_times = [scenario.event_by_id[event_id].time for event_id in activity.required_events]
        not_before = max([earliest_window_start, *event_times]) or None
        resource_reqs = [
            {"resource_type": resource_id, "quantity": quantity}
            for resource_id, quantity in activity.resource_reqs
        ]
        activity_groups = package_groups["activity_by_member"].get(activity_id, [])
        state_groups: list[dict[str, Any]] = []
        seen_state_groups: set[int] = set()
        for state_id in activity.output_state_ids:
            for group in package_groups["state_by_member"].get(state_id, []):
                if group["state_group_id"] in seen_state_groups:
                    continue
                seen_state_groups.add(group["state_group_id"])
                state_groups.append(group)
        rule = rule_by_id[node.op_rule_id]
        steps.append(StepData(
            step_order=node.id,
            op_rule_id=node.op_rule_id,
            op_rule_code=rule.code,
            op_rule_name=rule.name,
            duration_min=activity.duration,
            resource_reqs=resource_reqs,
            resource_type=resource_reqs[0]["resource_type"] if resource_reqs else "NONE",
            resource_qty=resource_reqs[0]["quantity"] if resource_reqs else 0,
            not_before=not_before,
            activity_continuity_groups=activity_groups,
            state_continuity_groups=state_groups,
            start_windows=start_windows,
        ))
    return RagData(candidate_plan_id=0, steps=steps, edges=list(pop.edges))


def _ancestor_steps(edges: list[tuple[int, int]], step_ids: list[int]) -> dict[int, set[int]]:
    direct: dict[int, set[int]] = {step_id: set() for step_id in step_ids}
    for before, after in edges:
        direct.setdefault(after, set()).add(before)
    result: dict[int, set[int]] = {}
    for step_id in step_ids:
        pending = list(direct.get(step_id, set()))
        seen: set[int] = set()
        while pending:
            current = pending.pop()
            if current in seen:
                continue
            seen.add(current)
            pending.extend(direct.get(current, set()))
        result[step_id] = seen
    return result


def _activity_start_windows(scenario: Any, activity: Any, predecessor_outputs: set[str]) -> list[tuple[int, int | None]]:
    windows: list[tuple[int, int | None]] = [(0, None)]
    for event_id in activity.required_events:
        windows = _intersect_windows(windows, [(scenario.event_by_id[event_id].time, None)])
    for state_id in activity.precondition_state_ids:
        if state_id in predecessor_outputs:
            continue
        if state_id not in scenario.initial_state_ids and not any(
            state_id in event.add_state_ids for event in scenario.external_events
        ):
            continue
        windows = _intersect_windows(windows, _state_availability_windows(scenario, state_id))
    return windows or [(1, 0)]


def _state_availability_windows(scenario: Any, state_id: str) -> list[tuple[int, int | None]]:
    active = state_id in scenario.initial_state_ids
    opened_at: int | None = 0 if active else None
    windows: list[tuple[int, int | None]] = []
    for event in sorted(scenario.external_events, key=lambda item: (item.time, item.id)):
        if state_id in event.remove_state_ids and active:
            windows.append((opened_at or 0, event.time))
            active = False
            opened_at = None
        if state_id in event.add_state_ids and not active:
            active = True
            opened_at = event.time
    if active:
        windows.append((opened_at or 0, None))
    return windows


def _intersect_windows(
    left: list[tuple[int, int | None]],
    right: list[tuple[int, int | None]],
) -> list[tuple[int, int | None]]:
    result: list[tuple[int, int | None]] = []
    for left_start, left_end in left:
        for right_start, right_end in right:
            start = max(left_start, right_start)
            if left_end is None:
                end = right_end
            elif right_end is None:
                end = left_end
            else:
                end = min(left_end, right_end)
            if end is None or start <= end:
                result.append((start, end))
    return result


def _package_group_metadata(payload: dict[str, Any]) -> dict[str, dict[str, list[dict[str, Any]]]]:
    activity_packages = {item["id"]: item for item in payload.get("activity_packages", [])}
    state_packages = {item["id"]: item for item in payload.get("state_packages", [])}
    all_ids = sorted({*activity_packages, *state_packages})
    numeric_ids = {package_id: index for index, package_id in enumerate(all_ids, start=1)}

    def ancestors(package_id: str, packages: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        current = packages.get(package_id)
        while current and current["id"] not in seen:
            seen.add(current["id"])
            result.append(current)
            current = packages.get(current.get("parent_id"))
        return result

    activity_by_member: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for membership in payload.get("activity_package_memberships", []):
        for package in ancestors(membership["package_id"], activity_packages):
            activity_by_member[membership["activity_id"]].append({
                "activity_group_id": numeric_ids[package["id"]],
                "activity_group_code": package.get("display_code") or package["id"],
                "activity_group_name": package.get("name"),
            })

    state_by_member: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for membership in payload.get("state_package_memberships", []):
        for package in ancestors(membership["state_package_id"], state_packages):
            state_by_member[membership["state_id"]].append({
                "state_group_id": numeric_ids[package["id"]],
                "state_group_code": package.get("display_code") or package["id"],
                "state_group_name": package.get("name"),
                "state_group_level": package.get("level"),
                "parent_state_group_id": numeric_ids.get(package.get("parent_id")),
            })
    return {"activity_by_member": activity_by_member, "state_by_member": state_by_member}


def _apply_execution_mode_constraints(
    schedule_model: Any,
    rag_data: RagData,
    activity_by_rule_id: dict[int, str],
    activity_by_id: dict[str, Any],
    execution_mode: str,
) -> None:
    if execution_mode == "serial":
        schedule_model.model.add_no_overlap([item.interval for item in schedule_model.task_vars.values()])
        return
    steps = {step.step_order: step for step in rag_data.steps}
    step_ids = sorted(steps)
    for index, left_id in enumerate(step_ids):
        left = activity_by_id[activity_by_rule_id[steps[left_id].op_rule_id]]
        left_reads = set(left.required_state_ids)
        left_writes = set(left.transition_state_ids) | set(left.output_state_ids)
        for right_id in step_ids[index + 1:]:
            right = activity_by_id[activity_by_rule_id[steps[right_id].op_rule_id]]
            right_reads = set(right.required_state_ids)
            right_writes = set(right.transition_state_ids) | set(right.output_state_ids)
            if left_writes & (right_reads | right_writes) or right_writes & left_reads:
                schedule_model.model.add_no_overlap([
                    schedule_model.task_vars[left_id].interval,
                    schedule_model.task_vars[right_id].interval,
                ])


def _extract_tasks(
    solver: cp_model.CpSolver,
    schedule_model: Any,
    rag_data: RagData,
    resources: list[ResourceData],
) -> list[TaskResult]:
    predecessor_map: dict[int, list[int]] = {step.step_order: [] for step in rag_data.steps}
    for before, after in rag_data.edges:
        predecessor_map.setdefault(after, []).append(before)
    step_map = {step.step_order: step for step in rag_data.steps}
    tasks: list[TaskResult] = []
    for step_order, task_var in schedule_model.task_vars.items():
        step = step_map[step_order]
        tasks.append(TaskResult(
            step_order=step_order,
            op_rule_id=step.op_rule_id,
            op_rule_code=step.op_rule_code,
            op_rule_name=step.op_rule_name,
            start_min=solver.value(task_var.start),
            end_min=solver.value(task_var.end),
            duration_min=step.duration_min,
            predecessors=predecessor_map.get(step_order, []),
            resources=[],
            resource_type=step.resource_type,
            resource_reqs=step.resource_reqs,
            state_continuity_groups=step.state_continuity_groups,
            elapsed_min=step.duration_min,
        ))
    tasks.sort(key=lambda item: (item.start_min, item.op_rule_code, item.step_order))
    _assign_resources(tasks, resources)
    return tasks


def _replay_schedule(
    simulator: Any,
    tasks: list[TaskResult],
    activity_by_rule_id: dict[int, str],
    Action: Any,
    execution_mode: str,
) -> Any:
    if execution_mode == "serial":
        state = simulator.initial_state()
        for task in tasks:
            state = _replay_serial_when_enabled(
                simulator,
                state,
                Action("EXECUTE", activity_id=activity_by_rule_id[task.op_rule_id]),
            )
        return _advance_to_goal(simulator, state)

    pending = list(tasks)
    state = simulator.initial_state()
    while pending:
        starting = [task for task in pending if task.start_min == state.time]
        if starting:
            for task in sorted(starting, key=lambda item: activity_by_rule_id[item.op_rule_id]):
                state = simulator.transition(
                    state,
                    Action("START", activity_id=activity_by_rule_id[task.op_rule_id]),
                )
                pending.remove(task)
            continue
        next_start = min(task.start_min for task in pending)
        advances = [action for action in simulator.enabled_actions(state) if action.kind == "ADVANCE"]
        if not advances:
            raise RuntimeError(f"Scheduler start at {next_start} cannot be replayed from time {state.time}")
        advance = advances[0]
        if advance.target_time > next_start:
            raise RuntimeError(f"Scheduler introduced unsupported idle time before {next_start}")
        state = simulator.transition(state, advance)
    return _advance_to_goal(simulator, state)


def _replay_serial_when_enabled(simulator: Any, state: Any, action: Any) -> Any:
    while True:
        try:
            return simulator.transition(state, action)
        except Exception as exc:
            waits = [item for item in simulator.enabled_actions(state) if item.kind in {"WAIT", "ADVANCE"}]
            if not waits:
                raise exc
            state = simulator.transition(state, waits[0])


def _advance_to_goal(simulator: Any, state: Any) -> Any:
    while not simulator.is_goal(state):
        advances = [action for action in simulator.enabled_actions(state) if action.kind in {"WAIT", "ADVANCE"}]
        if not advances:
            break
        state = simulator.transition(state, advances[0])
    return state


def _event_only_result(simulator: Any, modules: dict[str, Any], *, run_id: str, pathfinder_diagnostics: dict[str, Any]) -> Any:
    state = _advance_to_goal(simulator, simulator.initial_state())
    if not simulator.is_goal(state):
        return modules["EngineResult"](
            algorithm="LEGACY",
            run_id=run_id,
            seed=None,
            status="EXHAUSTED_EMPTY",
            stats={"pathfinder": pathfinder_diagnostics},
            diagnosis={"error_code": "EVENT_GOAL_NOT_REACHED", "error_message": "No activity or event reaches the target"},
        )
    candidate = simulator.candidate_from_state(
        state,
        algorithm="LEGACY",
        run_id=run_id,
        seed=None,
        discovered_at_seconds=0.0,
        normalize=False,
    )
    return modules["EngineResult"](
        algorithm="LEGACY",
        run_id=run_id,
        seed=None,
        status="OK",
        paths=(candidate,),
        first_solution_seconds=0.0,
        stats={"pathfinder": pathfinder_diagnostics, "scheduler": {"status": "NOT_REQUIRED"}},
    )


def _scheduler_stats(
    solver: cp_model.CpSolver,
    status: Any,
    schedule_model: Any,
    rag_data: RagData,
    tasks: list[TaskResult],
    objectives: list[dict[str, Any]],
) -> dict[str, Any]:
    makespan = int(solver.value(schedule_model.makespan))
    graph = build_schedule_graph(tasks, rag_data.edges, makespan)
    return {
        "status": solver.status_name(status),
        "makespan": makespan,
        "wall_time_seconds": round(float(solver.wall_time), 6),
        "branches": solver.num_branches,
        "parallel_groups": _detect_actual_parallel(tasks),
        "critical_path": compute_critical_path(graph),
        "objectives": objectives,
        "objective_terms": schedule_model.objective_cache.get("metadata", []),
        "tasks": [
            {
                "step_order": task.step_order,
                "activity_id": task.op_rule_code,
                "start_min": task.start_min,
                "end_min": task.end_min,
                "predecessors": task.predecessors,
            }
            for task in tasks
        ],
    }
