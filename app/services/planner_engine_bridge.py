"""Bridge one immutable Planner scenario into legacy POP+CP-SAT, A*, and GA engines."""

from __future__ import annotations

import os
import sys
import time
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
        raw = run_legacy_pipeline(
            scenario,
            budget,
            source_payload=expanded,
            run_id=run_id,
            modules=modules,
            objectives=objectives,
        )
    else:
        raise PlannerScenarioError("UNKNOWN_ENGINE", f"Unsupported engine: {engine}")
    validated = modules["validated_result"](raw, scenario)
    result = modules["to_primitive"](validated)
    result["elapsed_seconds"] = round(time.perf_counter() - started, 6)
    result["scenario_hash"] = scenario_hash(source_scenario)
    result["input_schema"] = "planner-shared-scenario/v1"
    result["validator_shared"] = True
    result["engine_pipeline"] = {
        "LEGACY": "partial_order_pathfinder+cp_sat_scheduler",
        "ASTAR": "anytime_astar_temporal_search",
        "GA": "genetic_temporal_search",
    }[engine]
    result["requested_objectives"] = objectives or DEFAULT_OBJECTIVES
    result["applied_objectives"] = (
        objectives or DEFAULT_OBJECTIVES
        if engine == "LEGACY"
        else [{"type": "engine_native_path_metrics", "weight": 1.0}]
    )
    return result


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
