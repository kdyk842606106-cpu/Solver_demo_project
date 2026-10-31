import copy

from app.services.planner_preflight import explain_unreachable_goals, reachable_states
from app.services.planner_scenarios import new_scenario, validate_scenario


def _scenario():
    scenario = new_scenario("模块调测")
    scenario["states"] = [
        {"id": key, "name": name}
        for key, name in [("installed", "模块 A 已安装"), ("on", "已上电"), ("off", "已下电"), ("tested", "模块 A 已调测")]
    ]
    scenario["initial_state_ids"] = ["installed"]
    scenario["goal_state_ids"] = ["tested"]
    scenario["activities"] = [
        _activity("power_on", "on", ["off"]),
        _activity("power_off", "off", ["on"]),
        _activity("test", "tested", ["on", "installed"]),
    ]
    return scenario


def _activity(identity, output, inputs):
    return {
        "id": identity, "name": identity, "duration": 1, "output_state_id": output,
        "preconditions": [{"state_id": value, "relation_role": "required"} for value in inputs],
    }


def _unreachable(scenario):
    return [item for item in validate_scenario(scenario) if item["code"] == "GOAL_STRUCTURALLY_UNREACHABLE"]


def test_cycle_reports_alternative_actual_facts_without_inventing_initial_states():
    scenario = _scenario()
    before = copy.deepcopy(scenario)
    issues = _unreachable(scenario)
    assert len(issues) == 1
    details = issues[0]["details"]
    assert details["state_name"] == "模块 A 已调测"
    assert details["blocked_activities"][0]["missing_preconditions"] == [{"id": "on", "name": "已上电"}]
    groups = details["confirmation_groups"]
    assert len(groups) == 1
    assert groups[0]["reason"] == "dependency_cycle"
    assert groups[0]["confirmable_state_ids"] == ["off", "on"]
    assert scenario["initial_state_ids"] == before["initial_state_ids"]
    for confirmed in ["on", "off"]:
        trial = copy.deepcopy(scenario)
        trial["initial_state_ids"].append(confirmed)
        assert validate_scenario(trial) == []


def test_multiple_missing_inputs_remain_separate_and_one_confirmation_is_not_enough():
    scenario = _scenario()
    scenario["states"].append({"id": "ready", "name": "工装就绪"})
    scenario["activities"][-1]["preconditions"].append({"state_id": "ready", "relation_role": "required"})
    groups = _unreachable(scenario)[0]["details"]["confirmation_groups"]
    assert {group["reason"] for group in groups} == {"dependency_cycle", "missing_initial_fact"}
    scenario["initial_state_ids"].append("on")
    groups = _unreachable(scenario)[0]["details"]["confirmation_groups"]
    assert len(groups) == 1
    assert groups[0]["confirmable_state_ids"] == ["ready"]
    scenario["initial_state_ids"].append("ready")
    assert validate_scenario(scenario) == []


def test_two_independent_cycles_can_be_confirmed_separately_or_together():
    scenario = _scenario()
    scenario["states"].extend([{"id": "locked", "name": "已锁定"}, {"id": "unlocked", "name": "已解锁"}])
    scenario["activities"].extend([
        _activity("lock", "locked", ["unlocked"]),
        _activity("unlock", "unlocked", ["locked"]),
    ])
    scenario["activities"][2]["preconditions"].append({"state_id": "locked", "relation_role": "required"})
    groups = _unreachable(scenario)[0]["details"]["confirmation_groups"]
    assert {tuple(group["confirmable_state_ids"]) for group in groups} == {("off", "on"), ("locked", "unlocked")}

    for power_state in ["off", "on"]:
        trial = copy.deepcopy(scenario)
        trial["initial_state_ids"].append(power_state)
        remaining = _unreachable(trial)[0]["details"]["confirmation_groups"]
        assert len(remaining) == 1
        assert remaining[0]["confirmable_state_ids"] == ["locked", "unlocked"]
        for lock_state in ["locked", "unlocked"]:
            complete = copy.deepcopy(trial)
            complete["initial_state_ids"].append(lock_state)
            assert validate_scenario(complete) == []


def test_linked_cycles_keep_the_unresolved_group_after_confirming_upstream():
    scenario = _scenario()
    scenario["states"].extend([{"id": "locked"}, {"id": "unlocked"}])
    scenario["activities"].extend([
        _activity("lock", "locked", ["unlocked", "on"]),
        _activity("unlock", "unlocked", ["locked", "on"]),
    ])
    scenario["goal_state_ids"] = ["locked"]
    groups = _unreachable(scenario)[0]["details"]["confirmation_groups"]
    assert len(groups) == 2
    scenario["initial_state_ids"].append("off")
    remaining = _unreachable(scenario)[0]["details"]["confirmation_groups"]
    assert len(remaining) == 1
    assert remaining[0]["confirmable_state_ids"] == ["locked", "unlocked"]
    scenario["initial_state_ids"].append("unlocked")
    assert validate_scenario(scenario) == []


def test_event_or_alternative_provider_breaks_cycle_without_prompt():
    scenario = _scenario()
    scenario["external_events"] = [{"id": "event", "time": 5, "add_state_ids": ["off"]}]
    assert validate_scenario(scenario) == []
    scenario["external_events"] = []
    scenario["activities"].append(_activity("alternative", "on", ["installed"]))
    assert validate_scenario(scenario) == []


def test_disabled_provider_is_configuration_issue_not_a_confirmation_suggestion():
    scenario = _scenario()
    scenario["activities"][0]["is_active"] = False
    group = _unreachable(scenario)[0]["details"]["confirmation_groups"][0]
    assert group["reason"] == "provider_unavailable"
    assert group["states"] == [{"id": "on", "name": "已上电"}]
    assert group["confirmable_state_ids"] == []
    assert group["provider_activities"] == [{"id": "power_on", "name": "power_on"}]


def test_forbidden_and_unknown_states_are_never_offered_for_confirmation():
    scenario = _scenario()
    scenario["forbidden_state_ids"] = ["off"]
    group = _unreachable(scenario)[0]["details"]["confirmation_groups"][0]
    assert group["confirmable_state_ids"] == ["on"]
    scenario["activities"][-1]["preconditions"] = [{"state_id": "missing", "relation_role": "required"}]
    group = _unreachable(scenario)[0]["details"]["confirmation_groups"][0]
    assert group["confirmable_state_ids"] == []


def test_scope_excluded_producer_does_not_make_goal_look_reachable():
    from app.services.planner_scenarios import add_membership, create_package

    scenario = _scenario()
    scenario["initial_state_ids"].append("off")
    root = create_package(scenario, {"name": "范围"}, display_number=1)
    child = create_package(scenario, {"name": "调测", "parent_id": root["id"]}, display_number=2)
    add_membership(scenario, child["id"], "test")
    scenario["activity_package_scope_ids"] = [root["id"]]
    group = _unreachable(scenario)[0]["details"]["confirmation_groups"][0]
    assert group["reason"] == "provider_unavailable"
    assert group["confirmable_state_ids"] == []


def test_self_cycle_and_unrelated_cycle_are_handled_without_suggesting_unrelated_facts():
    scenario = _scenario()
    scenario["activities"][0]["preconditions"][0]["state_id"] = "on"
    scenario["activities"].append(_activity("unrelated", "unrelated", ["unrelated"]))
    group = _unreachable(scenario)[0]["details"]["confirmation_groups"][0]
    assert group["reason"] == "dependency_cycle"
    assert group["confirmable_state_ids"] == ["on"]


def test_diagnostics_handle_long_chains_iteratively_and_preserve_input():
    activities = [_activity(f"a{i}", f"s{i}", [f"s{i + 1}"]) for i in range(1200)]
    scenario = {"activities": activities, "states": [{"id": f"s{i}"} for i in range(1201)]}
    before = copy.deepcopy(scenario)
    reachable = reachable_states(activities, set())
    detail = explain_unreachable_goals(scenario, activities, reachable, {"s0"})["s0"]
    assert detail["confirmation_groups"][0]["confirmable_state_ids"] == ["s1200"]
    assert scenario == before
