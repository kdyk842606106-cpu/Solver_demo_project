import pytest

from app.planner_worker import solve_child


@pytest.mark.parametrize("options,seconds", [
    ({"effective_budget": {"time_limit_seconds": 120}, "budget": {"time_limit_seconds": 2}}, 120),
    ({"budget": {"time_limit_seconds": 0}}, 0),
    ({}, 60),
])
def test_child_uses_frozen_budget_with_legacy_fallback(monkeypatch, options, seconds):
    observed = {}

    def run_engine(scenario, **kwargs):
        observed.update(kwargs)
        return {"status": "OPTIMAL"}

    class Connection:
        def send(self, message):
            observed['message'] = message

        def close(self):
            observed['closed'] = True

    monkeypatch.setattr('app.services.planner_engine_bridge.run_engine', run_engine)
    solve_child(Connection(), {'id': 'test', 'request': {
        'effective_scenario_snapshot': {}, 'seed': 11, 'objectives': [], **options,
    }})
    assert observed['budget_override'] == {'time_limit_seconds': seconds}
    assert observed['message'] == ({'status': 'OPTIMAL'}, None)
    assert observed['closed'] is True
