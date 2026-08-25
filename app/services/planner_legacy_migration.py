"""Preview and convert legacy layered data into the Planner common subset."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.modeling import is_atomic_state
from app.db.models import (
    ActivityPackageAtomicRef,
    ActivityNode,
    ActivityStateBinding,
    AtomicActivity,
    Machine,
    OpRule,
    Resource,
    StateNode,
)
from app.services.planner_scenarios import (
    add_membership,
    create_activity,
    create_package,
    new_scenario,
    rebuild_mirror,
    technical_id,
    validate_scenario,
)


async def build_legacy_migration(
    db: AsyncSession, machine_type_id: int, *, scenario_name: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    packages = list((await db.execute(
        select(ActivityNode).where(ActivityNode.machine_type_id == machine_type_id, ActivityNode.level.in_([1, 2])).order_by(ActivityNode.level, ActivityNode.sort_order, ActivityNode.id)
    )).scalars().all())
    atomics = list((await db.execute(
        select(AtomicActivity).where(AtomicActivity.machine_type_id == machine_type_id).options(
            selectinload(AtomicActivity.op_rules).selectinload(OpRule.preconditions),
            selectinload(AtomicActivity.op_rules).selectinload(OpRule.effects),
            selectinload(AtomicActivity.op_rules).selectinload(OpRule.resource_reqs),
        ).order_by(AtomicActivity.sort_order, AtomicActivity.id)
    )).scalars().all())
    refs = list((await db.execute(
        select(ActivityPackageAtomicRef).join(ActivityNode, ActivityPackageAtomicRef.activity_node_id == ActivityNode.id).where(ActivityNode.machine_type_id == machine_type_id).order_by(ActivityPackageAtomicRef.sort_order, ActivityPackageAtomicRef.id)
    )).scalars().all())
    states = list((await db.execute(select(StateNode).where(StateNode.machine_type_id == machine_type_id))).scalars().all())
    bindings = list((await db.execute(select(ActivityStateBinding).where(ActivityStateBinding.machine_type_id == machine_type_id))).scalars().all())
    resources = list((await db.execute(
        select(Resource).join(Machine, Resource.machine_id == Machine.id).where(Machine.machine_type_id == machine_type_id)
    )).scalars().all())

    report: dict[str, Any] = {
        "machine_type_id": machine_type_id,
        "source_counts": {"activity_packages": len(packages), "atomic_activities": len(atomics), "package_refs": len(refs), "state_nodes": len(states), "bindings": len(bindings), "resource_rows": len(resources)},
        "create_counts": {},
        "warnings": [],
        "blockers": [],
        "legacy_tables_mutated": False,
    }
    scenario = new_scenario(scenario_name)
    scenario["provenance"].update({"migration": "legacy-layered-to-planner-v1", "legacy_machine_type_id": str(machine_type_id)})

    package_map: dict[int, dict[str, Any]] = {}
    for index, package in enumerate(packages, start=1):
        parent = package_map.get(package.parent_id)
        if package.level == 2 and parent is None:
            report["blockers"].append(_item("PACKAGE_PARENT_MISSING", package.code, "二级活动包缺少可迁移的一级父包"))
            continue
        created = create_package(scenario, {"name": package.name, "parent_id": parent["id"] if parent else None, "sort_order": package.sort_order, "is_active": package.is_active}, display_number=index)
        created["legacy"] = {"table": "activity_node", "id": package.id, "code": package.code}
        package_map[package.id] = created

    state_map: dict[int, str] = {}
    state_by_id = {item.id: item for item in states}
    for state in states:
        if not is_atomic_state(state):
            continue
        state_id = technical_id("state")
        state_map[state.id] = state_id
        scenario["states"].append({"id": state_id, "name": state.name, "state_kind": "legacy_atomic", "legacy": {"table": "state_node", "id": state.id, "code": state.code, "feature_key": state.feature_key, "target_value": state.target_value}})

    capacity_by_type: dict[str, int] = defaultdict(int)
    for resource in resources:
        if resource.is_available:
            capacity_by_type[resource.resource_type] += int(resource.capacity)
    resource_map: dict[str, str] = {}
    for resource_type, capacity in sorted(capacity_by_type.items()):
        resource_id = technical_id("resource")
        resource_map[resource_type] = resource_id
        scenario["resources"].append({"id": resource_id, "name": resource_type, "capacity": capacity, "is_active": True, "legacy_resource_type": resource_type})

    bindings_by_atomic: dict[int, list[ActivityStateBinding]] = defaultdict(list)
    for binding in bindings:
        if binding.atomic_activity_id is not None:
            bindings_by_atomic[binding.atomic_activity_id].append(binding)
        elif binding.activity_node_id is not None:
            report["warnings"].append(_item("LEGACY_PACKAGE_BINDING_SKIPPED", str(binding.id), "活动包级状态绑定不进入新求解模型"))

    activity_map: dict[int, dict[str, Any]] = {}
    for index, atomic in enumerate(atomics, start=1):
        active_rules = [rule for rule in atomic.op_rules if rule.is_active]
        if len(active_rules) != 1:
            report["blockers"].append(_item("ACTIVE_RULE_COUNT_UNSUPPORTED", atomic.code, f"公共子集要求每个活动恰有一条启用规则，当前为 {len(active_rules)}"))
            continue
        rule = active_rules[0]
        unsupported_preconditions = [item for item in rule.preconditions if item.operator != "eq"]
        unsupported_effects = [item for item in rule.effects if item.effect_type not in {"set", "reset"}]
        if unsupported_preconditions or unsupported_effects:
            report["blockers"].append(_item("RULE_OUTSIDE_COMMON_SUBSET", atomic.code, "规则含非 eq 前置或数值/增量效果"))
            continue
        atomic_bindings = bindings_by_atomic.get(atomic.id, [])
        input_bindings = [item for item in atomic_bindings if item.binding_role in {"input", "context_input"}]
        output_bindings = [item for item in atomic_bindings if item.binding_role in {"output", "declared_output"}]
        if any(item.binding_type == "state_package" for item in atomic_bindings):
            report["blockers"].append(_item("STATE_PACKAGE_BINDING_UNSUPPORTED", atomic.code, "状态包绑定必须先展开为明确原子状态"))
            continue
        effect_keys = {item.feature_key for item in rule.effects}
        preconditions = []
        for binding in input_bindings:
            state = state_by_id.get(binding.state_node_id)
            state_id = state_map.get(binding.state_node_id)
            if state is None or state_id is None:
                report["blockers"].append(_item("ATOMIC_STATE_MISSING", atomic.code, f"输入绑定 {binding.id} 未指向可迁移原子状态"))
                continue
            preconditions.append({"state_id": state_id, "relation_role": "transition" if state.feature_key in effect_keys else "required"})
        additional_outputs = [state_map[item.state_node_id] for item in output_bindings if item.state_node_id in state_map]
        has_transition = any(item["relation_role"] == "transition" for item in preconditions)
        if not has_transition:
            report["warnings"].append(_item("MILESTONE_INFERRED", atomic.code, "规则没有替换输入，迁移为里程碑活动"))
        resource_reqs = {}
        for req in rule.resource_reqs:
            resource_id = resource_map.get(req.resource_type)
            if resource_id is None:
                report["blockers"].append(_item("RESOURCE_CAPACITY_MISSING", atomic.code, f"资源类型 {req.resource_type} 没有可用容量"))
            else:
                resource_reqs[resource_id] = int(req.quantity)
        created = create_activity(scenario, {"name": atomic.name, "duration": int(rule.duration_min), "preconditions": preconditions, "additional_output_state_ids": additional_outputs, "resource_reqs": resource_reqs, "event_reqs": [], "is_milestone": not has_transition, "is_active": atomic.is_active}, display_number=index)
        created["legacy"] = {"table": "atomic_activity", "id": atomic.id, "code": atomic.code, "op_rule_id": rule.id}
        activity_map[atomic.id] = created

    for ref in refs:
        package = package_map.get(ref.activity_node_id)
        activity = activity_map.get(ref.atomic_activity_id)
        if package is None or activity is None:
            report["warnings"].append(_item("PACKAGE_MEMBER_SKIPPED", str(ref.id), "包或活动被阻断，成员关系未迁移"))
            continue
        if package["level"] != 2:
            report["blockers"].append(_item("PACKAGE_MEMBER_LEVEL_INVALID", str(ref.id), "活动成员只能加入二级活动包"))
            continue
        add_membership(scenario, package["id"], activity["id"], sort_order=ref.sort_order)

    rebuild_mirror(scenario)
    report["create_counts"] = {
        "activity_packages": len(scenario["activity_packages"]),
        "state_packages": len(scenario["state_packages"]),
        "activities": len(scenario["activities"]),
        "states": len(scenario["states"]),
        "activity_memberships": len(scenario["activity_package_memberships"]),
        "state_memberships": len(scenario["state_package_memberships"]),
        "capacity_resources": len(scenario["resources"]),
    }
    if not report["blockers"]:
        report["validation_issues"] = validate_scenario(scenario)
        if report["validation_issues"]:
            report["blockers"].append(_item("MIGRATED_SCENARIO_INVALID", "scenario", "迁移结果未通过 Planner 公共校验"))
    else:
        report["validation_issues"] = []
    report["executable"] = not report["blockers"]
    return scenario, report


def _item(code: str, object_id: str, message: str) -> dict[str, Any]:
    return {"code": code, "object_id": object_id, "message": message}
