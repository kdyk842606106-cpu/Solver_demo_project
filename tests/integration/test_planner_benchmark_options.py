"""The experiment options are opt-in and cover POP, construction and replay."""
import time
from types import SimpleNamespace

import pytest

from app.services import planner_legacy_engine as legacy
from app.services.planner_engine_bridge import _planner_modules, planner_available, run_engine


@pytest.fixture(autouse=True)
def setup_db():
    """These in-memory adapter tests deliberately need no SQL connection."""
    if not planner_available():
        pytest.skip("external planner checkout is unavailable")
    _planner_modules()


def simple_scenario():
    from planner_experiment.benchmark_suite.golden import golden_instances
    return golden_instances()[0]["scenario"]


def test_legacy_receives_only_budget_remaining_after_pop(monkeypatch):
    original_pop = legacy.partial_order_plan
    observed = {}

    def slow_pop(**kwargs):
        time.sleep(0.05)
        return original_pop(**kwargs)

    class UnknownSolver:
        def __init__(self):
            self.parameters = SimpleNamespace()

        def solve(self, model):
            observed.update(vars(self.parameters))
            return legacy.cp_model.UNKNOWN

        def status_name(self, status):
            return "UNKNOWN"

        wall_time = 0.0
        num_branches = 0

    monkeypatch.setattr(legacy, "partial_order_plan", slow_pop)
    monkeypatch.setattr(legacy.cp_model, "CpSolver", UnknownSolver)
    run_engine(simple_scenario(), engine="LEGACY", run_id="remaining-budget", seed=23,
               budget_override={"time_limit_seconds": 1},
               run_options={"end_to_end_deadline": True, "worker_threads": 1, "trace_memory": False})
    assert 0 < observed["max_time_in_seconds"] < 0.96
    assert observed["num_search_workers"] == 1
    assert observed["random_seed"] == 23


@pytest.mark.parametrize("engine", ["LEGACY", "ASTAR", "GA"])
def test_optional_observer_emits_replayable_candidates_and_preserves_input(engine):
    import copy
    from planner_experiment.validator import ResultValidator
    from planner_experiment.scenario import scenario_from_dict

    payload = simple_scenario()
    before = copy.deepcopy(payload)
    seen, stamps = [], []
    result = run_engine(payload, engine=engine, run_id="observed", seed=11,
                        budget_override={"time_limit_seconds": 0.5, "transition_limit": 1000},
                        candidate_observer=seen.append,
                        run_options={"end_to_end_deadline": True, "worker_threads": 1, "trace_memory": False,
                                     "on_start": stamps.append})
    assert payload == before
    assert len(stamps) == 1
    assert seen
    assert all(ResultValidator(scenario_from_dict(payload)).validate(c).valid for c in seen)
    assert result["paths"]
