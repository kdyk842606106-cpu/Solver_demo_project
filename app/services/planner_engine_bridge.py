"""Bridge one immutable Planner scenario into legacy, A*, GA and joint CP-SAT."""

from __future__ import annotations

import copy
import os
import sys
import time
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import replace
from pathlib import Path
from typing import Any

from app.services.planner_legacy_engine import DEFAULT_OBJECTIVES, run_legacy_pipeline
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
    objectives: list[dict[str, Any]] | None = None,
    run_options: dict[str, Any] | None = None,
    candidate_observer: Callable[[Any], None] | None = None,
    progress_observer: Callable | None = None,
) -> dict[str, Any]:
    # Validation canonicalizes lists and compatibility flags; never mutate a
    # caller's authoritative scenario or persisted historical snapshot.
    source_scenario = copy.deepcopy(source_scenario)
    from app.services.planner_rules import exclusivity_enabled
    if exclusivity_enabled(source_scenario) and engine != 'JOINT_CP_SAT':
        raise PlannerScenarioError('UNSUPPORTED', '作业独占规则目前仅支持联合 CP-SAT')
    if (source_scenario.get('work_calendar_id') or (source_scenario.get('night_lift_rule') or {}).get('enabled')) and engine != 'JOINT_CP_SAT':
        raise PlannerScenarioError('UNSUPPORTED', '工作日历及夜班吊装规则目前仅支持联合 CP-SAT')
    issues = validate_scenario(copy.deepcopy(source_scenario))
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
    options = dict(run_options or {}, progress_observer=progress_observer)
    deadline = started + budget.time_limit_seconds if options.get("end_to_end_deadline") or engine == "JOINT_CP_SAT" else None
    if options.get("on_start") is not None:
        options["on_start"](started)
    context = nullcontext()
    if run_options is not None or candidate_observer is not None:
        from planner_experiment.instrumentation import observe_candidates
        context = observe_candidates(candidate_observer, trace_memory=options.get("trace_memory", True))
    with context:
        raw = _run_prepared_engine(modules, scenario, budget, expanded, engine, run_id, seed,
                                   objectives, options, deadline, candidate_observer)
    if engine == "LEGACY" and candidate_observer is not None:
        for candidate in raw.paths:
            candidate_observer(candidate)
    validation_scenario = scenario
    if engine == "JOINT_CP_SAT" and raw.paths:
        # Replay the same derived calendars, daylight domains and time windows
        # used by the model, including night-only scenarios without time_windows.
        from app.core.joint_cpsat import prepare_payload
        validation_scenario = modules["scenario_from_dict"](prepare_payload(expanded))
    validated = modules["validated_result"](raw, validation_scenario)
    result = modules["to_primitive"](validated)
    result["elapsed_seconds"] = round(time.perf_counter() - started, 6)
    result["scenario_hash"] = scenario_hash(source_scenario)
    result["input_schema"] = f"planner-shared-scenario/v{source_scenario.get('schema_version', 1)}"
    result["validator_shared"] = True
    result["engine_pipeline"] = {
        "LEGACY": "partial_order_pathfinder+cp_sat_scheduler",
        "ASTAR": "anytime_astar_temporal_search",
        "GA": "genetic_temporal_search",
        "JOINT_CP_SAT": "joint_state_planning_cp_sat+validated_normalization",
    }[engine]
    result["requested_objectives"] = objectives or DEFAULT_OBJECTIVES
    result["applied_objectives"] = (
        objectives or DEFAULT_OBJECTIVES
        if engine == "LEGACY"
        else [{"type": "engine_native_path_metrics", "weight": 1.0}]
    )
    if engine == "JOINT_CP_SAT":
        result["applied_objectives"] = [{"type": "minimize_makespan", "weight": 1.0}]
        if result["stats"].get("validator_rejected"):
            result["stats"]["proven_optimal"] = False
        result["proven_optimal"] = bool(result["stats"].get("proven_optimal"))
        result["proven_infeasible"] = bool(result["stats"].get("proven_infeasible"))
        result["lower_bound"] = result["stats"].get("lower_bound")
        result["validator_time_windows"] = len(expanded.get("time_windows") or []) + len(expanded.get("run_time_windows") or [])
    return result


def _run_prepared_engine(
    modules: dict[str, Any], scenario: Any, budget: Any, expanded: dict[str, Any],
    engine: str, run_id: str, seed: int, objectives: list[dict[str, Any]] | None,
    options: dict[str, Any], deadline: float | None,
    candidate_observer: Callable[[Any], None] | None = None,
) -> Any:
    if (expanded.get("time_windows") or expanded.get("run_time_windows")) and engine != "JOINT_CP_SAT":
        return modules["EngineResult"](engine, run_id, seed, "UNSUPPORTED",
            diagnosis={"error_code": "ENGINE_TIME_WINDOWS_UNSUPPORTED", "error_message": "此引擎尚未接入活动硬时间窗口，请选择联合 CP-SAT"})
    if engine == "ASTAR":
        explorer = modules["AnytimeAStar"](scenario)
        if deadline is not None:
            budget = replace(budget, time_limit_seconds=max(0.0, deadline - time.perf_counter()))
        raw = explorer.run(scenario, budget, run_id=run_id, seed=None)
    elif engine == "GA":
        explorer = modules["GeneticExplorer"](scenario)
        if deadline is not None:
            budget = replace(budget, time_limit_seconds=max(0.0, deadline - time.perf_counter()))
        raw = explorer.run(scenario, budget, run_id=run_id, seed=seed)
    elif engine == "LEGACY":
        raw = run_legacy_pipeline(
            scenario,
            budget,
            source_payload=expanded,
            run_id=run_id,
            modules=modules,
            objectives=objectives,
            deadline=deadline,
            worker_threads=options.get("worker_threads"),
            random_seed=seed if options.get("worker_threads") is not None else None,
        )
    elif engine == "JOINT_CP_SAT":
        from app.core.joint_cpsat import solve_joint
        raw = solve_joint(expanded, run_id=run_id, seed=seed, budget=budget,
                          deadline=deadline, candidate_observer=candidate_observer,
                          progress_observer=options.get("progress_observer"),
                          worker_threads=options.get("worker_threads"))
    else:
        raise PlannerScenarioError("UNKNOWN_ENGINE", f"Unsupported engine: {engine}")
    return raw


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
    from planner_experiment import scenario as scenario_module

    if "independent-delete-effects/v1" not in getattr(scenario_module, "ENGINE_CAPABILITIES", ()):
        raise PlannerEngineUnavailable("Planner engine is outdated; independent-delete-effects/v1 is required")
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
