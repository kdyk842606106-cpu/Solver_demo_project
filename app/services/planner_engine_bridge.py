"""Bridge one immutable Planner scenario into legacy BFS, A*, and GA engines."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

from app.core.planner.bfs import BfsLimits, forward_bfs_plan
from app.db.models import OpRule, OpRuleEffect, OpRulePrecond, StateFeatureDef
from app.services.planner_scenarios import PlannerScenarioError, expand_packages, scenario_hash, validate_scenario


class PlannerEngineUnavailable(RuntimeError):
    pass


def planner_project_path() -> Path:
    configured = os.getenv("PLANNER_PROJECT_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parents[2].parent / "planner"


def planner_available() -> bool:
    return (planner_project_path() / "planner_experiment" / "scenario.py").is_file()


def run_engine(
    source_scenario: dict[str, Any],
    *,
    engine: str,
    run_id: str,
    seed: int,
    budget_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues = validate_scenario(source_scenario)
    if issues:
        raise PlannerScenarioError("SCENARIO_INVALID", "Scenario failed preflight", details={"issues": issues})
    expanded = expand_packages(source_scenario)
    modules = _planner_modules()
    scenario = modules["scenario_from_dict"](expanded)
    configured = dict(expanded.get("default_budget") or {})
    configured.update(budget_override or {})
    budget = modules["Budget"](
        time_limit_seconds=float(configured.get("time_limit_seconds", 5.0)),
        transition_limit=int(configured.get("transition_limit", 20000)),
        max_solutions=int(configured.get("max_solutions", 20)),
    )
    started = time.perf_counter()
    if engine == "ASTAR":
        raw = modules["AnytimeAStar"](scenario).run(scenario, budget, run_id=run_id, seed=None)
    elif engine == "GA":
        raw = modules["GeneticExplorer"](scenario).run(scenario, budget, run_id=run_id, seed=seed)
    elif engine == "LEGACY":
        raw = _run_legacy(scenario, budget, run_id=run_id, modules=modules)
    else:
        raise PlannerScenarioError("UNKNOWN_ENGINE", f"Unsupported engine: {engine}")
    validated = modules["validated_result"](raw, scenario)
    result = modules["to_primitive"](validated)
    result["elapsed_seconds"] = round(time.perf_counter() - started, 6)
    result["scenario_hash"] = scenario_hash(source_scenario)
    result["input_schema"] = "planner-shared-scenario/v1"
    result["validator_shared"] = True
    return result


def _run_legacy(scenario, budget, *, run_id: str, modules: dict[str, Any]):
    """Run the real legacy forward-BFS core against a boolean state adapter.

    Capacity resources and event time do not affect legacy path selection; the
    shared Planner simulator applies them during replay.  This preserves the
    legacy planner's role while keeping final legality under one validator.
    """
    state_ids = sorted(scenario.state_by_id)
    current = {state_id: "inactive" for state_id in state_ids}
    for state_id in scenario.initial_state_ids:
        current[state_id] = "active"
    # Event-provided facts are available to legacy path selection.  The shared
    # simulator inserts the real wait before replaying the selected activity.
    for event in scenario.external_events:
        for state_id in event.add_state_ids:
            current[state_id] = "active"
    target = dict(current)
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
    rules: list[OpRule] = []
    activity_by_rule_id: dict[int, str] = {}
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
                id=index * 1000 + rel_index,
                op_rule_id=index,
                feature_key=relation.state_id,
                operator="eq",
                feature_value="active",
            )
            for rel_index, relation in enumerate(activity.precondition_bindings, start=1)
        ]
        effects = []
        effect_index = 1
        for state_id in activity.transition_state_ids:
            effects.append(
                OpRuleEffect(
                    id=index * 1000 + effect_index,
                    op_rule_id=index,
                    feature_key=state_id,
                    new_value="inactive",
                    effect_type="set",
                )
            )
            effect_index += 1
        for state_id in activity.output_state_ids:
            effects.append(
                OpRuleEffect(
                    id=index * 1000 + effect_index,
                    op_rule_id=index,
                    feature_key=state_id,
                    new_value="active",
                    effect_type="set",
                )
            )
            effect_index += 1
        rule.effects = effects
        rules.append(rule)
        activity_by_rule_id[index] = activity.id

    bfs = forward_bfs_plan(
        current,
        target,
        rules,
        feature_defs,
        limits=BfsLimits(max_depth=scenario.max_steps, max_nodes=max(2000, int(budget.transition_limit))),
    )
    if bfs.status != "success":
        return modules["EngineResult"](
            algorithm="LEGACY",
            run_id=run_id,
            seed=None,
            status="EXHAUSTED_EMPTY" if bfs.error_code != "BFS_LIMIT_EXCEEDED" else "TIMEOUT_EMPTY",
            stats=bfs.diagnostics,
            diagnosis={"error_code": bfs.error_code, "error_message": bfs.error_message},
        )

    simulator = modules["PathSimulator"](scenario)
    state = simulator.initial_state()
    try:
        for transition in bfs.path:
            action = modules["Action"]("EXECUTE", activity_id=activity_by_rule_id[transition.rule.id])
            state = _replay_when_enabled(simulator, state, action)
        while not simulator.is_goal(state):
            wait_actions = [action for action in simulator.enabled_actions(state) if action.kind in {"WAIT", "ADVANCE"}]
            if not wait_actions:
                break
            state = simulator.transition(state, wait_actions[0])
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
            status="OK" if simulator.is_goal(state) else "EXHAUSTED_EMPTY",
            paths=(candidate,) if simulator.is_goal(state) else (),
            first_solution_seconds=0.0 if simulator.is_goal(state) else None,
            stats={**bfs.diagnostics, "adapter": "planner-state-to-legacy-boolean-v1"},
        )
    except Exception as exc:
        return modules["EngineResult"](
            algorithm="LEGACY",
            run_id=run_id,
            seed=None,
            status="ERROR",
            stats=bfs.diagnostics,
            diagnosis={"error_code": "LEGACY_REPLAY_FAILED", "error_message": str(exc)},
            error=str(exc),
        )


def _replay_when_enabled(simulator, state, action):
    while True:
        try:
            return simulator.transition(state, action)
        except Exception as exc:
            wait_actions = [item for item in simulator.enabled_actions(state) if item.kind in {"WAIT", "ADVANCE"}]
            if not wait_actions:
                raise exc
            state = simulator.transition(state, wait_actions[0])


def _planner_modules() -> dict[str, Any]:
    root = planner_project_path()
    if not (root / "planner_experiment" / "scenario.py").is_file():
        raise PlannerEngineUnavailable(
            f"Planner project not found at {root}; set PLANNER_PROJECT_PATH to the planner repository"
        )
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    from planner_experiment.astar import AnytimeAStar
    from planner_experiment.ga import GeneticExplorer
    from planner_experiment.models import Action, Budget, EngineResult, to_primitive
    from planner_experiment.runner import _validated_result
    from planner_experiment.scenario import scenario_from_dict
    from planner_experiment.simulator import PathSimulator

    return {
        "Action": Action,
        "AnytimeAStar": AnytimeAStar,
        "Budget": Budget,
        "EngineResult": EngineResult,
        "GeneticExplorer": GeneticExplorer,
        "PathSimulator": PathSimulator,
        "scenario_from_dict": scenario_from_dict,
        "to_primitive": to_primitive,
        "validated_result": _validated_result,
    }
