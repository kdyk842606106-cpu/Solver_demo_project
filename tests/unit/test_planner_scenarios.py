import copy
from time import perf_counter

import pytest

from app.services.planner_scenarios import (
    PlannerScenarioError,
    add_membership,
    create_activity,
    create_package,
    expand_packages,
    graph_projection,
    new_scenario,
    normalize_import,
    rebuild_mirror,
    update_activity,
    validate_scenario,
)


def _modeled_scenario():
    scenario = new_scenario("包镜像测试")
    root = create_package(scenario, {"name": "总装", "parent_id": None}, display_number=1)
    left = create_package(scenario, {"name": "准备", "parent_id": root["id"]}, display_number=2)
    right = create_package(scenario, {"name": "复核", "parent_id": root["id"]}, display_number=3)
    seed_id = "state:seed:test"
    scenario["states"].append({"id": seed_id, "name": "初始", "state_kind": "seed"})
    scenario["initial_state_ids"].append(seed_id)
    first = create_activity(
        scenario,
        {
            "name": "准备活动",
            "duration": 2,
            "preconditions": [{"state_id": seed_id, "relation_role": "transition"}],
        },
        display_number=1,
    )
    second = create_activity(
        scenario,
        {
            "name": "复核活动",
            "duration": 1,
            "preconditions": [{"state_id": first["output_state_id"], "relation_role": "transition"}],
        },
        display_number=2,
    )
    first_ref = add_membership(scenario, left["id"], first["id"])
    add_membership(scenario, right["id"], first["id"])
    add_membership(scenario, right["id"], second["id"])
    scenario["target_activity_package_ids"] = [root["id"]]
    rebuild_mirror(scenario)
    return scenario, root, left, right, first, second, first_ref


def test_packages_have_read_only_one_to_one_state_mirrors_and_reusable_members():
    scenario, root, left, right, first, _, _ = _modeled_scenario()

    assert len(scenario["state_packages"]) == len(scenario["activity_packages"]) == 3
    state_by_source = {item["source_activity_package_id"]: item for item in scenario["state_packages"]}
    assert state_by_source[left["id"]]["parent_id"] == state_by_source[root["id"]]["id"]
    first_state_refs = [
        item for item in scenario["state_package_memberships"] if item["state_id"] == first["output_state_id"]
    ]
    assert len(first_state_refs) == 2
    assert all(item["managed_by"] == "activity_package_mirror" for item in first_state_refs)


def test_package_target_expands_all_members_once_and_graph_has_only_activity_nodes():
    scenario, _, _, _, first, second, _ = _modeled_scenario()
    expanded = expand_packages(scenario)
    graph = graph_projection(scenario)

    assert expanded["target_activity_ids"] == sorted([first["id"], second["id"]])
    assert "state_packages" not in expanded
    assert graph["summary"]["state_node_count"] == 0
    assert graph["nodes"]
    assert {item["kind"] for item in graph["nodes"]} == {"activity"}
    assert all(item["kind"] == "activity_dependency" for item in graph["edges"])
    assert any(item["state_id"] == first["output_state_id"] for item in graph["edges"])


def test_invalid_package_levels_and_empty_targets_are_blocked():
    scenario = new_scenario("错误包")
    root = create_package(scenario, {"name": "一级"}, display_number=1)
    child = create_package(scenario, {"name": "二级", "parent_id": root["id"]}, display_number=2)
    with pytest.raises(PlannerScenarioError, match="Only two"):
        create_package(scenario, {"name": "三级", "parent_id": child["id"]}, display_number=3)
    scenario["target_activity_package_ids"] = [root["id"]]
    with pytest.raises(PlannerScenarioError, match="no activities"):
        expand_packages(scenario)


def test_import_without_ids_rewrites_references_and_preserved_mirror_is_checked():
    scenario, *_ = _modeled_scenario()
    regenerated = normalize_import(scenario, preserve_ids=False)
    assert regenerated["id"] != scenario["id"]
    assert validate_scenario(regenerated) == []

    corrupted = copy.deepcopy(scenario)
    corrupted["state_packages"][0]["name"] = "被篡改"
    with pytest.raises(PlannerScenarioError, match="inconsistent"):
        normalize_import(corrupted, preserve_ids=True)


def test_activity_identity_rename_clone_and_delete_rules():
    scenario, _, _, _, first, _, _ = _modeled_scenario()
    original_id = first["id"]
    original_output = first["output_state_id"]

    renamed = update_activity(scenario, original_id, {"name": "准备（改名）"})
    assert renamed["id"] == original_id
    assert renamed["output_state_id"] == original_output
    assert renamed["output_state_name"] == "准备（改名）完成"

    customized = update_activity(scenario, original_id, {"output_state_name": "已就绪"})
    update_activity(scenario, original_id, {"name": "再次改名"})
    assert customized["output_state_name"] == "已就绪"

    from app.services.planner_scenarios import clone_activity
    cloned = clone_activity(scenario, original_id, display_number=3)
    assert cloned["id"] != original_id
    assert cloned["output_state_id"] != original_output
    assert cloned["display_code"] == "ACT-0003"


def test_activity_milestone_flag_is_derived_from_dependency_roles():
    scenario = new_scenario("活动类型自动识别")
    seed_id = "state:seed:derived-type"
    scenario["states"].append({"id": seed_id, "name": "准备完成", "state_kind": "seed"})
    scenario["initial_state_ids"].append(seed_id)

    retained = create_activity(
        scenario,
        {
            "name": "保留前置活动",
            "duration": 2,
            "preconditions": [{"state_id": seed_id, "relation_role": "required"}],
            "is_milestone": False,
        },
        display_number=1,
    )
    transitioned = create_activity(
        scenario,
        {
            "name": "替换前置活动",
            "duration": 2,
            "preconditions": [{"state_id": seed_id, "relation_role": "transition"}],
            "is_milestone": True,
        },
        display_number=2,
    )
    assert retained["is_milestone"] is True
    assert transitioned["is_milestone"] is False

    update_activity(
        scenario,
        retained["id"],
        {
            "preconditions": [{"state_id": seed_id, "relation_role": "transition"}],
            "is_milestone": True,
        },
    )
    update_activity(
        scenario,
        transitioned["id"],
        {
            "preconditions": [{"state_id": seed_id, "relation_role": "required"}],
            "is_milestone": False,
        },
    )
    assert retained["is_milestone"] is False
    assert transitioned["is_milestone"] is True

    imported = copy.deepcopy(scenario)
    for activity in imported["activities"]:
        activity["is_milestone"] = not activity["is_milestone"]
    normalized = normalize_import(imported, preserve_ids=False)
    flags = {item["name"]: item["is_milestone"] for item in normalized["activities"]}
    assert flags == {"保留前置活动": False, "替换前置活动": True}

    validation_copy = copy.deepcopy(imported)
    assert validate_scenario(validation_copy) == []
    assert {item["name"]: item["is_milestone"] for item in validation_copy["activities"]} == flags


def test_validation_rejects_cycles_dangling_members_and_conflicting_goals():
    scenario, root, child, _, first, _, _ = _modeled_scenario()
    root["parent_id"] = child["id"]
    root["level"] = 2
    child["parent_id"] = root["id"]
    scenario["activity_package_memberships"].append({
        "id": "activity-package-member:dangling",
        "package_id": "activity-package:missing",
        "activity_id": first["id"],
        "sort_order": 0,
        "layout": {},
    })
    scenario["goal_state_ids"] = [first["output_state_id"]]
    scenario["forbidden_state_ids"] = [first["output_state_id"]]

    codes = {item["code"] for item in validate_scenario(scenario)}
    assert "PACKAGE_CYCLE" in codes
    assert "PACKAGE_NOT_FOUND" in codes

    conflict = new_scenario("冲突目标")
    conflict["states"] = [{"id": "state:seed:conflict", "name": "冲突", "state_kind": "seed"}]
    conflict["initial_state_ids"] = ["state:seed:conflict"]
    conflict["goal_state_ids"] = ["state:seed:conflict"]
    conflict["forbidden_state_ids"] = ["state:seed:conflict"]
    assert "CONFLICTING_GOAL" in {item["code"] for item in validate_scenario(conflict)}


def test_activity_only_projection_handles_100_activities_20_packages_and_cycles():
    scenario = new_scenario("规模与循环")
    seed_id = "state:seed:scale"
    scenario["states"].append({"id": seed_id, "name": "开始", "state_kind": "seed"})
    scenario["initial_state_ids"].append(seed_id)
    children = []
    for index in range(10):
        root = create_package(scenario, {"name": f"一级{index}"}, display_number=index * 2 + 1)
        children.append(create_package(scenario, {"name": f"二级{index}", "parent_id": root["id"]}, display_number=index * 2 + 2))

    previous_state = seed_id
    activities = []
    for index in range(100):
        activity = create_activity(
            scenario,
            {"name": f"活动{index}", "duration": 1, "preconditions": [{"state_id": previous_state, "relation_role": "transition"}]},
            display_number=index + 1,
        )
        add_membership(scenario, children[index // 10]["id"], activity["id"])
        activities.append(activity)
        previous_state = activity["output_state_id"]

    started = perf_counter()
    graph = graph_projection(scenario)
    elapsed = perf_counter() - started
    assert graph["summary"] == {"activity_count": 100, "display_node_count": 100, "package_count": 20, "state_node_count": 0}
    assert len(graph["edges"]) == 99
    assert elapsed < 1.0

    # Projection is a bounded pass over relations, so dependency cycles render
    # as ordinary activity edges and never enter a recursive layout algorithm.
    activities[0]["preconditions"] = [{"state_id": activities[-1]["output_state_id"], "relation_role": "transition"}]
    cyclic = graph_projection(scenario)
    assert len(cyclic["edges"]) == 100
