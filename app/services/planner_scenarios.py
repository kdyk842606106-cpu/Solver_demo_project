"""Planner shared-scenario domain service.

The service deliberately keeps the new Planner workspace separate from the
legacy machine knowledge tables.  Activity packages are user-managed display
containers; state packages are a read-only mirror rebuilt on every write.
"""

from __future__ import annotations

import copy
import hashlib
import json
from collections import defaultdict
from typing import Any, Iterable
from uuid import UUID, uuid4


SCHEMA_VERSION = 1
MANAGED_STATE_PACKAGE = "activity_package_mirror"


class PlannerScenarioError(ValueError):
    def __init__(self, code: str, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}


def technical_id(kind: str, identity: UUID | None = None) -> str:
    return f"{kind}:{identity or uuid4()}"


def paired_id(kind: str, source_id: str) -> str:
    try:
        suffix = source_id.rsplit(":", 1)[1]
        UUID(suffix)
    except (IndexError, ValueError) as exc:
        raise PlannerScenarioError("INVALID_TECHNICAL_ID", f"Invalid technical ID: {source_id}") from exc
    return f"{kind}:{suffix}"


def derived_milestone(preconditions: Iterable[dict[str, Any]]) -> bool:
    """Keep the engine compatibility flag derived from dependency roles."""
    return not any(item.get("relation_role") == "transition" for item in preconditions)


def synchronize_activity_milestones(scenario: dict[str, Any]) -> None:
    for activity in scenario.get("activities", []):
        activity["is_milestone"] = derived_milestone(activity.get("preconditions", []))


def new_scenario(name: str, *, display_code: str | None = None) -> dict[str, Any]:
    scenario_id = technical_id("scenario")
    return {
        "schema_version": SCHEMA_VERSION,
        "id": scenario_id,
        "display_code": display_code or f"SCN-{scenario_id[-8:].upper()}",
        "name": name.strip(),
        "execution_mode": "serial",
        "start_time": 0,
        "max_steps": 20,
        "default_budget": {"time_limit_seconds": 5.0, "transition_limit": 20000, "max_solutions": 20},
        "states": [],
        "initial_state_ids": [],
        "goal_state_ids": [],
        "forbidden_state_ids": [],
        "target_activity_ids": [],
        "target_activity_package_ids": [],
        "activity_package_scope_ids": [],
        "activities": [],
        "activity_packages": [],
        "activity_package_memberships": [],
        "state_packages": [],
        "state_package_memberships": [],
        "resources": [],
        "external_events": [],
        "provenance": {"source": "solver_demo_project", "schema": "planner-shared-scenario/v1"},
    }


def create_activity(
    scenario: dict[str, Any], payload: dict[str, Any], *, display_number: int
) -> dict[str, Any]:
    activity_uuid = uuid4()
    activity_id = technical_id("activity", activity_uuid)
    name = str(payload["name"]).strip()
    activity = {
        "id": activity_id,
        "display_code": f"ACT-{display_number:04d}",
        "name": name,
        "duration": int(payload.get("duration", 1)),
        "preconditions": copy.deepcopy(payload.get("preconditions", [])),
        "output_state_id": technical_id("state", activity_uuid) + ":output",
        "output_state_name": f"{name}完成",
        "output_name_customized": False,
        "additional_output_state_ids": list(payload.get("additional_output_state_ids", [])),
        "resource_reqs": dict(payload.get("resource_reqs", {})),
        "event_reqs": list(payload.get("event_reqs", [])),
        "max_instances": payload.get("max_instances"),
        "is_milestone": derived_milestone(payload.get("preconditions", [])),
        "is_active": bool(payload.get("is_active", True)),
    }
    if activity["duration"] <= 0:
        raise PlannerScenarioError("INVALID_DURATION", "Activity duration must be positive")
    scenario.setdefault("activities", []).append(activity)
    scenario.setdefault("states", []).append(
        {
            "id": activity["output_state_id"],
            "name": activity["output_state_name"],
            "source_activity_id": activity_id,
            "state_kind": "activity_output",
            "managed": True,
        }
    )
    if payload.get("is_target"):
        scenario.setdefault("target_activity_ids", []).append(activity_id)
    rebuild_mirror(scenario)
    return activity


def update_activity(scenario: dict[str, Any], activity_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    activity = require_item(scenario.get("activities", []), activity_id, "ACTIVITY_NOT_FOUND")
    old_name = activity["name"]
    for field in (
        "name", "duration", "preconditions", "additional_output_state_ids", "resource_reqs",
        "event_reqs", "max_instances", "is_active",
    ):
        if field in payload:
            activity[field] = copy.deepcopy(payload[field])
    activity["is_milestone"] = derived_milestone(activity.get("preconditions", []))
    if int(activity["duration"]) <= 0:
        raise PlannerScenarioError("INVALID_DURATION", "Activity duration must be positive")
    if "output_state_name" in payload:
        activity["output_state_name"] = str(payload["output_state_name"]).strip()
        activity["output_name_customized"] = True
    elif activity["name"] != old_name and not activity.get("output_name_customized"):
        activity["output_state_name"] = f"{activity['name']}完成"
    state = find_item(scenario.get("states", []), activity["output_state_id"])
    if state is not None:
        state["name"] = activity["output_state_name"]
    if "is_target" in payload:
        toggle_value(scenario.setdefault("target_activity_ids", []), activity_id, bool(payload["is_target"]))
    rebuild_mirror(scenario)
    return activity


def update_event(scenario: dict[str, Any], event_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    event = require_item(scenario.get("external_events", []), event_id, "EVENT_NOT_FOUND")
    if "name" in payload:
        name = str(payload["name"]).strip()
        if not name:
            raise PlannerScenarioError("EVENT_NAME_REQUIRED", "External event name is required")
        event["name"] = name
    if "time" in payload:
        time = int(payload["time"])
        if time < 0:
            raise PlannerScenarioError("INVALID_EVENT_TIME", "External event time cannot be negative")
        event["time"] = time
    for field in ("add_state_ids", "remove_state_ids"):
        if field in payload:
            event[field] = list(payload[field])
    return event


def clone_activity(
    scenario: dict[str, Any], activity_id: str, *, display_number: int
) -> dict[str, Any]:
    source = require_item(scenario.get("activities", []), activity_id, "ACTIVITY_NOT_FOUND")
    payload = {
        key: copy.deepcopy(value)
        for key, value in source.items()
        if key not in {"id", "display_code", "output_state_id", "output_state_name", "output_name_customized"}
    }
    payload["name"] = f"{source['name']}副本"
    created = create_activity(scenario, payload, display_number=display_number)
    created["output_state_name"] = f"{created['name']}完成"
    return created


def delete_activity(scenario: dict[str, Any], activity_id: str) -> None:
    activity = require_item(scenario.get("activities", []), activity_id, "ACTIVITY_NOT_FOUND")
    output_ids = {activity["output_state_id"], *activity.get("additional_output_state_ids", [])}
    consumers = [
        item["id"]
        for item in scenario.get("activities", [])
        if item["id"] != activity_id
        and any(rel.get("state_id") in output_ids for rel in item.get("preconditions", []))
    ]
    if consumers:
        raise PlannerScenarioError(
            "BODY_IN_USE", "Activity output is used by another activity", details={"consumer_activity_ids": consumers}
        )
    scenario["activities"] = [item for item in scenario.get("activities", []) if item["id"] != activity_id]
    scenario["states"] = [item for item in scenario.get("states", []) if item["id"] not in output_ids]
    scenario["activity_package_memberships"] = [
        item for item in scenario.get("activity_package_memberships", []) if item["activity_id"] != activity_id
    ]
    for key in ("target_activity_ids",):
        scenario[key] = [value for value in scenario.get(key, []) if value != activity_id]
    rebuild_mirror(scenario)


def create_package(
    scenario: dict[str, Any], payload: dict[str, Any], *, display_number: int
) -> dict[str, Any]:
    parent_id = payload.get("parent_id")
    if parent_id:
        parent = require_item(scenario.get("activity_packages", []), parent_id, "PACKAGE_PARENT_NOT_FOUND")
        if int(parent["level"]) != 1:
            raise PlannerScenarioError("PACKAGE_DEPTH_EXCEEDED", "Only two activity-package levels are supported")
        level = 2
    else:
        level = 1
    package_uuid = uuid4()
    package = {
        "id": technical_id("activity-package", package_uuid),
        "display_code": f"AP-{display_number:04d}",
        "name": str(payload["name"]).strip(),
        "parent_id": parent_id,
        "level": level,
        "sort_order": int(payload.get("sort_order", 0)),
        "is_active": bool(payload.get("is_active", True)),
        "mirrored_state_package_id": technical_id("state-package", package_uuid),
        "layout": copy.deepcopy(payload.get("layout", {})),
    }
    scenario.setdefault("activity_packages", []).append(package)
    rebuild_mirror(scenario)
    return package


def update_package(scenario: dict[str, Any], package_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    package = require_item(scenario.get("activity_packages", []), package_id, "PACKAGE_NOT_FOUND")
    if "parent_id" in payload and payload["parent_id"] != package.get("parent_id"):
        parent_id = payload["parent_id"]
        if package["level"] == 1 and parent_id is not None:
            raise PlannerScenarioError("PACKAGE_LEVEL_IMMUTABLE", "A root package cannot be moved under another package")
        if package["level"] == 2:
            parent = require_item(scenario.get("activity_packages", []), parent_id, "PACKAGE_PARENT_NOT_FOUND")
            if parent["level"] != 1:
                raise PlannerScenarioError("PACKAGE_DEPTH_EXCEEDED", "Level-2 packages require a level-1 parent")
            package["parent_id"] = parent_id
    for field in ("name", "sort_order", "is_active", "layout"):
        if field in payload:
            package[field] = copy.deepcopy(payload[field])
    rebuild_mirror(scenario)
    return package


def delete_package(scenario: dict[str, Any], package_id: str) -> None:
    require_item(scenario.get("activity_packages", []), package_id, "PACKAGE_NOT_FOUND")
    if any(item.get("parent_id") == package_id for item in scenario.get("activity_packages", [])):
        raise PlannerScenarioError("PACKAGE_HAS_CHILDREN", "Remove child packages before deleting the parent")
    scenario["activity_packages"] = [item for item in scenario["activity_packages"] if item["id"] != package_id]
    scenario["activity_package_memberships"] = [
        item for item in scenario.get("activity_package_memberships", []) if item["package_id"] != package_id
    ]
    scenario["target_activity_package_ids"] = [
        item for item in scenario.get("target_activity_package_ids", []) if item != package_id
    ]
    scenario["activity_package_scope_ids"] = [
        item for item in scenario.get("activity_package_scope_ids", []) if item != package_id
    ]
    rebuild_mirror(scenario)


def add_membership(
    scenario: dict[str, Any], package_id: str, activity_id: str, *, sort_order: int = 0
) -> dict[str, Any]:
    package = require_item(scenario.get("activity_packages", []), package_id, "PACKAGE_NOT_FOUND")
    require_item(scenario.get("activities", []), activity_id, "ACTIVITY_NOT_FOUND")
    if int(package["level"]) != 2:
        raise PlannerScenarioError("PACKAGE_MEMBER_LEVEL_INVALID", "Activities can only be added to level-2 packages")
    memberships = scenario.setdefault("activity_package_memberships", [])
    if any(item["package_id"] == package_id and item["activity_id"] == activity_id for item in memberships):
        raise PlannerScenarioError("PACKAGE_MEMBER_DUPLICATE", "Activity is already a member of this package")
    membership = {
        "id": technical_id("activity-package-member"),
        "package_id": package_id,
        "activity_id": activity_id,
        "sort_order": int(sort_order),
        "layout": {},
    }
    memberships.append(membership)
    rebuild_mirror(scenario)
    return membership


def remove_membership(scenario: dict[str, Any], membership_id: str) -> None:
    require_item(scenario.get("activity_package_memberships", []), membership_id, "PACKAGE_MEMBER_NOT_FOUND")
    scenario["activity_package_memberships"] = [
        item for item in scenario["activity_package_memberships"] if item["id"] != membership_id
    ]
    rebuild_mirror(scenario)


def rebuild_mirror(scenario: dict[str, Any]) -> None:
    """Rebuild all read-only state packages from the authoritative activity side."""
    packages = scenario.get("activity_packages", [])
    activities = {item["id"]: item for item in scenario.get("activities", [])}
    state_packages = []
    by_activity_package: dict[str, str] = {
        package["id"]: package.get("mirrored_state_package_id") or paired_id("state-package", package["id"])
        for package in packages
    }
    for package in packages:
        mirror_id = by_activity_package[package["id"]]
        package["mirrored_state_package_id"] = mirror_id
        parent_id = package.get("parent_id")
        state_packages.append(
            {
                "id": mirror_id,
                "name": package["name"],
                "level": package["level"],
                "parent_id": by_activity_package.get(parent_id) if parent_id else None,
                "source_activity_package_id": package["id"],
                "managed_by": MANAGED_STATE_PACKAGE,
                "is_active": package.get("is_active", True),
            }
        )
    state_memberships = []
    for membership in scenario.get("activity_package_memberships", []):
        activity = activities.get(membership["activity_id"])
        state_package_id = by_activity_package.get(membership["package_id"])
        if activity is None or state_package_id is None:
            continue
        state_memberships.append(
            {
                "id": paired_id("state-package-member", membership["id"]),
                "state_package_id": state_package_id,
                "state_id": activity["output_state_id"],
                "source_membership_id": membership["id"],
                "managed_by": MANAGED_STATE_PACKAGE,
            }
        )
    scenario["state_packages"] = state_packages
    scenario["state_package_memberships"] = state_memberships
    canonicalize_lists(scenario)


def expand_packages(scenario: dict[str, Any]) -> dict[str, Any]:
    expanded = copy.deepcopy(scenario)
    synchronize_activity_milestones(expanded)
    packages = {item["id"]: item for item in expanded.get("activity_packages", [])}
    members_by_package: dict[str, set[str]] = defaultdict(set)
    for membership in expanded.get("activity_package_memberships", []):
        members_by_package[membership["package_id"]].add(membership["activity_id"])
    children: dict[str, list[str]] = defaultdict(list)
    for package in packages.values():
        if package.get("parent_id"):
            children[package["parent_id"]].append(package["id"])

    def activity_ids(package_id: str, stack: tuple[str, ...] = ()) -> set[str]:
        if package_id in stack:
            raise PlannerScenarioError("PACKAGE_CYCLE", "Activity-package hierarchy contains a cycle")
        if package_id not in packages:
            raise PlannerScenarioError("PACKAGE_NOT_FOUND", f"Unknown package: {package_id}")
        values = set(members_by_package.get(package_id, set()))
        for child_id in children.get(package_id, []):
            values.update(activity_ids(child_id, (*stack, package_id)))
        return values

    # Runtime goals are expressed exclusively as state facts.  Target activity
    # fields remain empty compatibility placeholders in the v1 wire contract.
    expanded["target_activity_ids"] = []

    scope_package_ids = expanded.get("activity_package_scope_ids", [])
    if scope_package_ids:
        scope_ids: set[str] = set()
        for package_id in scope_package_ids:
            scope_ids.update(activity_ids(package_id))
        expanded["activities"] = [item for item in expanded.get("activities", []) if item["id"] in scope_ids]

    expanded["activities"] = [item for item in expanded.get("activities", []) if item.get("is_active", True)]
    for item in expanded["activities"]:
        for key in ("display_code", "output_name_customized", "is_active"):
            item.pop(key, None)
    expanded["resources"] = [item for item in expanded.get("resources", []) if item.get("is_active", True)]
    for item in expanded["resources"]:
        item.pop("is_active", None)
    for key in (
        "display_code", "states", "activity_packages", "activity_package_memberships",
        "state_packages", "state_package_memberships", "target_activity_package_ids",
        "activity_package_scope_ids",
    ):
        expanded.pop(key, None)
    return expanded


def validate_scenario(scenario: dict[str, Any]) -> list[dict[str, Any]]:
    synchronize_activity_milestones(scenario)
    issues: list[dict[str, Any]] = []
    # Check the authoritative package side before rebuilding its managed mirror.
    # Rebuilding deliberately skips dangling memberships, so doing this first is
    # required to report corrupt imports instead of silently hiding them.
    packages = {item.get("id"): item for item in scenario.get("activity_packages", []) if item.get("id")}
    activity_ids = {item.get("id") for item in scenario.get("activities", []) if item.get("id")}
    for package in packages.values():
        package_id = package["id"]
        parent_id = package.get("parent_id")
        level = int(package.get("level", 0))
        if level == 1 and parent_id is not None:
            issues.append(issue("PACKAGE_LEVEL_INVALID", "A level-1 package cannot have a parent", object_id=package_id))
        elif level == 2:
            parent = packages.get(parent_id)
            if parent is None:
                issues.append(issue("PACKAGE_PARENT_NOT_FOUND", "Level-2 package parent does not exist", object_id=package_id, details={"parent_id": parent_id}))
            elif int(parent.get("level", 0)) != 1:
                issues.append(issue("PACKAGE_DEPTH_EXCEEDED", "Level-2 package requires a level-1 parent", object_id=package_id))
        elif level not in {1, 2}:
            issues.append(issue("PACKAGE_LEVEL_INVALID", "Only two activity-package levels are supported", object_id=package_id))

        seen: set[str] = set()
        cursor = package
        while cursor and cursor.get("parent_id"):
            current_id = cursor["id"]
            if current_id in seen:
                issues.append(issue("PACKAGE_CYCLE", "Activity-package hierarchy contains a cycle", object_id=package_id))
                break
            seen.add(current_id)
            cursor = packages.get(cursor.get("parent_id"))

    membership_pairs: set[tuple[str, str]] = set()
    for membership in scenario.get("activity_package_memberships", []):
        package_id = membership.get("package_id")
        activity_id = membership.get("activity_id")
        package = packages.get(package_id)
        if package is None:
            issues.append(issue("PACKAGE_NOT_FOUND", "Membership references an unknown package", object_id=membership.get("id"), details={"package_id": package_id}))
        elif int(package.get("level", 0)) != 2:
            issues.append(issue("PACKAGE_MEMBER_LEVEL_INVALID", "Activities can only be added to level-2 packages", object_id=membership.get("id")))
        if activity_id not in activity_ids:
            issues.append(issue("ACTIVITY_NOT_FOUND", "Membership references an unknown activity", object_id=membership.get("id"), details={"activity_id": activity_id}))
        pair = (package_id, activity_id)
        if pair in membership_pairs:
            issues.append(issue("PACKAGE_MEMBER_DUPLICATE", "Activity is already a member of this package", object_id=membership.get("id")))
        membership_pairs.add(pair)

    if issues:
        return issues
    try:
        rebuild_mirror(scenario)
        expanded = expand_packages(scenario)
    except PlannerScenarioError as exc:
        return [issue(exc.code, str(exc), details=exc.details)]

    ids_by_kind = {
        "activity": [item.get("id") for item in scenario.get("activities", [])],
        "state": [item.get("id") for item in scenario.get("states", [])],
        "package": [item.get("id") for item in scenario.get("activity_packages", [])],
        "resource": [item.get("id") for item in scenario.get("resources", [])],
        "event": [item.get("id") for item in scenario.get("external_events", [])],
    }
    for kind, values in ids_by_kind.items():
        duplicates = sorted({value for value in values if value and values.count(value) > 1})
        for value in duplicates:
            issues.append(issue("DUPLICATE_ID", f"Duplicate {kind} ID: {value}", object_id=value))

    states = set(ids_by_kind["state"])
    resources = {item["id"]: int(item["capacity"]) for item in scenario.get("resources", [])}
    events = set(ids_by_kind["event"])
    for key in ("initial_state_ids", "goal_state_ids", "forbidden_state_ids"):
        for state_id in scenario.get(key, []):
            if state_id not in states:
                issues.append(issue("UNKNOWN_STATE", f"{key} references an unknown state", object_id=state_id))
    conflict_states = set(scenario.get("goal_state_ids", [])) & set(scenario.get("forbidden_state_ids", []))
    for state_id in sorted(conflict_states):
        issues.append(issue("CONFLICTING_GOAL", "A state cannot be both required and forbidden", object_id=state_id))
    producers: dict[str, list[str]] = defaultdict(list)
    for activity in scenario.get("activities", []):
        if int(activity.get("duration", 0)) <= 0:
            issues.append(issue("INVALID_DURATION", "Activity duration must be positive", object_id=activity.get("id")))
        for relation in activity.get("preconditions", []):
            if relation.get("state_id") not in states:
                issues.append(issue("UNKNOWN_STATE", "Activity precondition references an unknown state", object_id=activity.get("id"), details={"state_id": relation.get("state_id")}))
            if relation.get("relation_role") not in {"required", "transition"}:
                issues.append(issue("INVALID_RELATION_ROLE", "Precondition role must be required or transition", object_id=activity.get("id")))
        for state_id in (activity.get("output_state_id"), *activity.get("additional_output_state_ids", [])):
            if state_id not in states:
                issues.append(issue("UNKNOWN_OUTPUT_STATE", "Activity output references an unknown state", object_id=activity.get("id"), details={"state_id": state_id}))
            elif state_id:
                producers[state_id].append(activity["id"])
        for resource_id, quantity in activity.get("resource_reqs", {}).items():
            if resource_id not in resources:
                issues.append(issue("UNKNOWN_RESOURCE", "Activity references an unknown resource", object_id=activity.get("id"), details={"resource_id": resource_id}))
            elif int(quantity) <= 0 or int(quantity) > resources[resource_id]:
                issues.append(issue("RESOURCE_CAPACITY_EXCEEDED", "Resource demand must be within aggregate capacity", object_id=activity.get("id"), details={"resource_id": resource_id}))
        for event_id in activity.get("event_reqs", []):
            if event_id not in events:
                issues.append(issue("UNKNOWN_EVENT", "Activity references an unknown event", object_id=activity.get("id"), details={"event_id": event_id}))

    for event in scenario.get("external_events", []):
        for state_id in (*event.get("add_state_ids", []), *event.get("remove_state_ids", [])):
            if state_id not in states:
                issues.append(issue("UNKNOWN_EVENT_STATE", "External event references an unknown state", object_id=event.get("id"), details={"state_id": state_id}))

    initially_available = set(scenario.get("initial_state_ids", []))
    event_available = {state_id for event in scenario.get("external_events", []) for state_id in event.get("add_state_ids", [])}
    target_states = set(scenario.get("goal_state_ids", []))
    target_activity_ids = set(expanded.get("target_activity_ids", []))
    activity_by_id = {item["id"]: item for item in scenario.get("activities", [])}
    for activity_id in target_activity_ids:
        activity = activity_by_id.get(activity_id)
        if activity is None:
            issues.append(issue("UNKNOWN_TARGET_ACTIVITY", "Target activity does not exist", object_id=activity_id))
        else:
            target_states.add(activity["output_state_id"])
    for state_id in target_states:
        if state_id not in initially_available and state_id not in event_available and state_id not in producers:
            issues.append(issue("GOAL_WITHOUT_PROVIDER", "Goal state has no provider", object_id=state_id))

    # An optimistic fixed point catches structurally unreachable goals without
    # pretending to solve transition consumption or resource scheduling here.
    reachable = initially_available | event_available
    changed = True
    while changed:
        changed = False
        for activity in scenario.get("activities", []):
            required = {item.get("state_id") for item in activity.get("preconditions", [])}
            if required <= reachable:
                outputs = {activity.get("output_state_id"), *activity.get("additional_output_state_ids", [])} - {None}
                if not outputs <= reachable:
                    reachable.update(outputs)
                    changed = True
    for state_id in sorted(target_states - reachable):
        issues.append(issue("GOAL_STRUCTURALLY_UNREACHABLE", "Goal state cannot be reached from initial or event states", object_id=state_id))

    if int(scenario.get("max_steps", 0)) <= 0:
        issues.append(issue("INVALID_MAX_STEPS", "max_steps must be positive"))
    if scenario.get("execution_mode") not in {"serial", "parallel"}:
        issues.append(issue("INVALID_EXECUTION_MODE", "execution_mode must be serial or parallel"))
    return issues


def graph_projection(scenario: dict[str, Any]) -> dict[str, Any]:
    activities = {item["id"]: item for item in scenario.get("activities", [])}
    packages = copy.deepcopy(scenario.get("activity_packages", []))
    memberships = scenario.get("activity_package_memberships", [])
    memberships_by_activity: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in memberships:
        memberships_by_activity[item["activity_id"]].append(item)
    nodes = []
    refs_by_activity: dict[str, list[str]] = defaultdict(list)
    for activity in activities.values():
        refs = memberships_by_activity.get(activity["id"], []) or [None]
        for membership in refs:
            graph_id = membership["id"] if membership else f"activity-body:{activity['id']}"
            refs_by_activity[activity["id"]].append(graph_id)
            nodes.append(
                {
                    "id": graph_id,
                    "kind": "activity",
                    "canonical_activity_id": activity["id"],
                    "package_id": membership["package_id"] if membership else None,
                    "display_code": activity["display_code"],
                    "name": activity["name"],
                    "duration": activity["duration"],
                    "is_target": activity["id"] in scenario.get("target_activity_ids", []),
                    "layout": copy.deepcopy(membership.get("layout", {})) if membership else {},
                    "seed_preconditions": [],
                    "event_preconditions": list(activity.get("event_reqs", [])),
                }
            )

    producers: dict[str, list[str]] = defaultdict(list)
    for activity in activities.values():
        for state_id in (activity["output_state_id"], *activity.get("additional_output_state_ids", [])):
            producers[state_id].append(activity["id"])
    node_by_id = {item["id"]: item for item in nodes}
    edges = []
    initial = set(scenario.get("initial_state_ids", []))
    event_states = {state for event in scenario.get("external_events", []) for state in event.get("add_state_ids", [])}
    for consumer in activities.values():
        for relation in consumer.get("preconditions", []):
            state_id = relation["state_id"]
            if state_id in initial:
                for ref_id in refs_by_activity[consumer["id"]]:
                    node_by_id[ref_id]["seed_preconditions"].append(state_id)
            if state_id in event_states:
                continue
            for provider_id in producers.get(state_id, []):
                for source_ref in refs_by_activity[provider_id]:
                    for target_ref in refs_by_activity[consumer["id"]]:
                        edges.append(
                            {
                                "id": f"dependency:{source_ref}:{target_ref}:{state_id}",
                                "kind": "activity_dependency",
                                "source": source_ref,
                                "target": target_ref,
                                "state_id": state_id,
                                "relation_role": relation.get("relation_role", "required"),
                                "provider_semantics": "OR",
                            }
                        )
    return {
        "scenario_id": scenario["id"],
        "revision": scenario.get("revision", 1),
        "containers": packages,
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "activity_count": len(activities),
            "display_node_count": len(nodes),
            "package_count": len(packages),
            "state_node_count": 0,
        },
    }


def scenario_hash(scenario: dict[str, Any]) -> str:
    payload = expand_packages(scenario)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def normalize_import(payload: dict[str, Any], *, preserve_ids: bool) -> dict[str, Any]:
    """Normalize imported JSON and regenerate every derived mirror object."""
    imported = copy.deepcopy(payload)
    synchronize_activity_milestones(imported)
    migrate_target_activities_to_goals(imported)
    if not preserve_ids:
        return _regenerate_import_ids(imported)
    _validate_import_ids(imported)
    rebuild_mirror(imported)
    return imported


def migrate_target_activities_to_goals(
    scenario: dict[str, Any], *, record_provenance: bool = False
) -> dict[str, Any]:
    """Convert legacy activity/package targets into state-fact goals in place."""
    target_activity_ids = list(scenario.get("target_activity_ids", []))
    target_package_ids = list(scenario.get("target_activity_package_ids", []))
    if not target_activity_ids and not target_package_ids:
        scenario["target_activity_ids"] = []
        scenario["target_activity_package_ids"] = []
        return scenario

    activities = {item.get("id"): item for item in scenario.get("activities", []) if item.get("id")}
    packages = {item.get("id"): item for item in scenario.get("activity_packages", []) if item.get("id")}
    members_by_package: dict[str, set[str]] = defaultdict(set)
    for membership in scenario.get("activity_package_memberships", []):
        members_by_package[membership.get("package_id")].add(membership.get("activity_id"))
    children: dict[str, list[str]] = defaultdict(list)
    for package in packages.values():
        if package.get("parent_id"):
            children[package["parent_id"]].append(package["id"])

    def members(package_id: str, stack: tuple[str, ...] = ()) -> set[str]:
        if package_id in stack:
            raise PlannerScenarioError("PACKAGE_CYCLE", "Activity-package hierarchy contains a cycle")
        if package_id not in packages:
            raise PlannerScenarioError("PACKAGE_NOT_FOUND", f"Unknown package: {package_id}")
        result = set(members_by_package.get(package_id, set()))
        for child_id in children.get(package_id, []):
            result.update(members(child_id, (*stack, package_id)))
        return result

    unknown_activity_ids = sorted(set(target_activity_ids) - set(activities))
    if unknown_activity_ids:
        raise PlannerScenarioError(
            "ACTIVITY_NOT_FOUND",
            "Target activity does not exist",
            details={"activity_ids": unknown_activity_ids},
        )

    converted_ids = set(target_activity_ids)
    for package_id in target_package_ids:
        converted_ids.update(members(package_id))
    converted_ids = {
        activity_id for activity_id in converted_ids
        if activities.get(activity_id, {}).get("is_active", True)
    }
    added_goal_state_ids = {
        activities[activity_id].get("output_state_id")
        for activity_id in converted_ids
        if activity_id in activities and activities[activity_id].get("output_state_id")
    }
    original_goals = list(scenario.get("goal_state_ids", []))
    scenario["goal_state_ids"] = sorted(set(original_goals) | added_goal_state_ids)
    scenario["target_activity_ids"] = []
    scenario["target_activity_package_ids"] = []
    if record_provenance:
        provenance = scenario.get("provenance")
        if not isinstance(provenance, dict):
            provenance = {}
            scenario["provenance"] = provenance
        provenance.setdefault("runtime_state_target_migration_v1", {
            "original_goal_state_ids": original_goals,
            "original_target_activity_ids": target_activity_ids,
            "original_target_activity_package_ids": target_package_ids,
            "added_goal_state_ids": sorted(added_goal_state_ids),
        })
    return scenario


def _regenerate_import_ids(payload: dict[str, Any]) -> dict[str, Any]:
    result = new_scenario(str(payload.get("name") or "导入场景"))
    result.update({key: copy.deepcopy(value) for key, value in payload.items() if key not in {
        "id", "display_code", "activities", "states", "activity_packages", "activity_package_memberships",
        "state_packages", "state_package_memberships",
    }})
    state_map: dict[str, str] = {}
    activity_map: dict[str, str] = {}
    package_map: dict[str, str] = {}
    resource_map: dict[str, str] = {}
    event_map: dict[str, str] = {}
    result["states"] = []
    for index, state in enumerate(payload.get("states", []), start=1):
        old_id = state.get("id") or f"S{index:03d}"
        new_id = technical_id("state")
        state_map[old_id] = new_id
        cloned = copy.deepcopy(state)
        cloned["id"] = new_id
        result["states"].append(cloned)
    result["activities"] = []
    for index, activity in enumerate(payload.get("activities", []), start=1):
        old_id = activity.get("id") or f"A{index:03d}"
        identity = uuid4()
        new_id = technical_id("activity", identity)
        activity_map[old_id] = new_id
        old_output = activity.get("output_state_id") or f"{old_id}:output"
        new_output = technical_id("state", identity) + ":output"
        state_map[old_output] = new_output
        cloned = copy.deepcopy(activity)
        cloned.update({"id": new_id, "display_code": f"ACT-{index:04d}", "output_state_id": new_output})
        result["activities"].append(cloned)
        if not any(item["id"] == new_output for item in result["states"]):
            result["states"].append({"id": new_output, "name": cloned.get("output_state_name") or f"{cloned['name']}完成", "source_activity_id": new_id, "state_kind": "activity_output", "managed": True})
    for activity in result["activities"]:
        for relation in activity.get("preconditions", []):
            relation["state_id"] = state_map.get(relation["state_id"], relation["state_id"])
        activity["additional_output_state_ids"] = [state_map.get(value, value) for value in activity.get("additional_output_state_ids", [])]
    result["resources"] = []
    for resource in payload.get("resources", []):
        old_id = resource.get("id") or f"R{len(resource_map) + 1:03d}"
        new_id = technical_id("resource")
        resource_map[old_id] = new_id
        result["resources"].append({**copy.deepcopy(resource), "id": new_id})
    result["external_events"] = []
    for event in payload.get("external_events", []):
        old_id = event.get("id") or f"E{len(event_map) + 1:03d}"
        new_id = technical_id("event")
        event_map[old_id] = new_id
        cloned = {**copy.deepcopy(event), "id": new_id}
        cloned["add_state_ids"] = [state_map.get(value, value) for value in cloned.get("add_state_ids", [])]
        cloned["remove_state_ids"] = [state_map.get(value, value) for value in cloned.get("remove_state_ids", [])]
        result["external_events"].append(cloned)
    for activity in result["activities"]:
        activity["resource_reqs"] = {resource_map.get(key, key): value for key, value in activity.get("resource_reqs", {}).items()}
        activity["event_reqs"] = [event_map.get(value, value) for value in activity.get("event_reqs", [])]
    result["activity_packages"] = []
    for index, package in enumerate(payload.get("activity_packages", []), start=1):
        old_id = package.get("id") or f"P{index:03d}"
        identity = uuid4()
        new_id = technical_id("activity-package", identity)
        package_map[old_id] = new_id
        cloned = copy.deepcopy(package)
        cloned.update({"id": new_id, "display_code": f"AP-{index:04d}", "mirrored_state_package_id": technical_id("state-package", identity)})
        result["activity_packages"].append(cloned)
    for package in result["activity_packages"]:
        package["parent_id"] = package_map.get(package.get("parent_id"), package.get("parent_id"))
    result["activity_package_memberships"] = []
    for membership in payload.get("activity_package_memberships", []):
        result["activity_package_memberships"].append({
            "id": technical_id("activity-package-member"),
            "package_id": package_map.get(membership["package_id"], membership["package_id"]),
            "activity_id": activity_map.get(membership["activity_id"], membership["activity_id"]),
            "sort_order": int(membership.get("sort_order", 0)),
            "layout": copy.deepcopy(membership.get("layout", {})),
        })
    for key in ("initial_state_ids", "goal_state_ids", "forbidden_state_ids"):
        result[key] = [state_map.get(value, value) for value in payload.get(key, [])]
    result["target_activity_ids"] = [activity_map.get(value, value) for value in payload.get("target_activity_ids", [])]
    result["target_activity_package_ids"] = [package_map.get(value, value) for value in payload.get("target_activity_package_ids", [])]
    result["activity_package_scope_ids"] = [package_map.get(value, value) for value in payload.get("activity_package_scope_ids", [])]
    result["id"] = technical_id("scenario")
    result["display_code"] = f"SCN-{result['id'][-8:].upper()}"
    rebuild_mirror(result)
    return result


def _validate_import_ids(payload: dict[str, Any]) -> None:
    for item in payload.get("state_packages", []):
        if item.get("managed_by") != MANAGED_STATE_PACKAGE:
            raise PlannerScenarioError("STATE_PACKAGE_NOT_MANAGED", "Imported state packages must be system mirrors")
    original_mirrors = copy.deepcopy(payload.get("state_packages", []))
    original_members = copy.deepcopy(payload.get("state_package_memberships", []))
    trial = copy.deepcopy(payload)
    rebuild_mirror(trial)
    if original_mirrors and _semantic_json(original_mirrors) != _semantic_json(trial["state_packages"]):
        raise PlannerScenarioError("STATE_PACKAGE_MIRROR_MISMATCH", "Imported state-package mirror is inconsistent")
    if original_members and _semantic_json(original_members) != _semantic_json(trial["state_package_memberships"]):
        raise PlannerScenarioError("STATE_PACKAGE_MEMBER_MIRROR_MISMATCH", "Imported state-package memberships are inconsistent")


def _semantic_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonicalize_lists(scenario: dict[str, Any]) -> None:
    for key in (
        "initial_state_ids", "goal_state_ids", "forbidden_state_ids", "target_activity_ids",
        "target_activity_package_ids", "activity_package_scope_ids",
    ):
        scenario[key] = sorted(set(scenario.get(key, [])))


def require_item(items: Iterable[dict[str, Any]], item_id: str | None, code: str) -> dict[str, Any]:
    item = find_item(items, item_id)
    if item is None:
        raise PlannerScenarioError(code, f"Object not found: {item_id}")
    return item


def find_item(items: Iterable[dict[str, Any]], item_id: str | None) -> dict[str, Any] | None:
    return next((item for item in items if item.get("id") == item_id), None)


def toggle_value(values: list[str], value: str, enabled: bool) -> None:
    if enabled and value not in values:
        values.append(value)
    elif not enabled:
        values[:] = [item for item in values if item != value]


def issue(code: str, message: str, *, object_id: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"severity": "error", "code": code, "message": message, "object_id": object_id, "details": details or {}}
