"""Maintenance intent joint solve service."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Machine, MachineState, MaintenanceIntentTemplate, StateFeatureDef
from app.db.schemas import LayeredSolveRequest, MaintenanceFactTemplate, MaintenanceSolveRequest
from app.services.layered_solve import solve_layered


def _error_payload(
    error_code: str,
    error_message: str,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "solve_request_id": None,
        "status": "failed",
        "error_code": error_code,
        "error_message": error_message,
        "diagnostics": diagnostics or {},
    }


def _unique_ints(values: list[int]) -> list[int]:
    result: list[int] = []
    seen: set[int] = set()
    for value in values:
        if value in seen:
            continue
        result.append(value)
        seen.add(value)
    return result


def _fact_from_json(payload: dict[str, Any]) -> MaintenanceFactTemplate:
    return MaintenanceFactTemplate.model_validate(payload)


async def _load_feature_keys(
    session: AsyncSession,
    machine_type_id: int,
) -> set[str]:
    result = await session.execute(
        select(StateFeatureDef.feature_key).where(StateFeatureDef.machine_type_id == machine_type_id)
    )
    return set(result.scalars().all())


def _validate_exact_fact(
    fact: MaintenanceFactTemplate,
    *,
    valid_feature_keys: set[str],
    purpose: str,
) -> dict[str, Any] | None:
    if fact.feature_key not in valid_feature_keys:
        return {
            "code": "UNKNOWN_FEATURE_KEY",
            "purpose": purpose,
            "feature_key": fact.feature_key,
        }
    if fact.operator != "eq":
        return {
            "code": "UNSUPPORTED_MAINTENANCE_FACT_OPERATOR",
            "purpose": purpose,
            "feature_key": fact.feature_key,
            "operator": fact.operator,
        }
    if fact.value is None:
        return {
            "code": "MISSING_MAINTENANCE_FACT_VALUE",
            "purpose": purpose,
            "feature_key": fact.feature_key,
        }
    return None


def _merge_observed_facts(
    facts: list[MaintenanceFactTemplate],
    *,
    valid_feature_keys: set[str],
) -> tuple[dict[str, str], list[dict[str, Any]]]:
    overrides: dict[str, str] = {}
    conflicts: list[dict[str, Any]] = []
    for fact in facts:
        issue = _validate_exact_fact(fact, valid_feature_keys=valid_feature_keys, purpose="observed")
        if issue is not None:
            conflicts.append(issue)
            continue
        assert fact.value is not None
        previous = overrides.get(fact.feature_key)
        if previous is not None and previous != fact.value:
            conflicts.append({
                "code": "CONFLICTING_MAINTENANCE_OBSERVED_FACT",
                "feature_key": fact.feature_key,
                "values": sorted({previous, fact.value}),
            })
            continue
        overrides[fact.feature_key] = fact.value
    return overrides, conflicts


def _merge_desired_facts(
    facts: list[MaintenanceFactTemplate],
    *,
    valid_feature_keys: set[str],
) -> tuple[list[MaintenanceFactTemplate], list[dict[str, Any]]]:
    by_key: dict[str, MaintenanceFactTemplate] = {}
    conflicts: list[dict[str, Any]] = []
    for fact in facts:
        issue = _validate_exact_fact(fact, valid_feature_keys=valid_feature_keys, purpose="desired")
        if issue is not None:
            conflicts.append(issue)
            continue
        assert fact.value is not None
        previous = by_key.get(fact.feature_key)
        if previous is not None and previous.value != fact.value:
            conflicts.append({
                "code": "CONFLICTING_MAINTENANCE_DESIRED_FACT",
                "feature_key": fact.feature_key,
                "values": sorted({str(previous.value), fact.value}),
            })
            continue
        by_key[fact.feature_key] = fact
    return list(by_key.values()), conflicts


def _template_summary(template: MaintenanceIntentTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "issue_type": template.issue_type,
        "name": template.name,
        "scope_activity_node_id": template.scope_activity_node_id,
        "target_state_node_ids": template.target_state_node_ids or [],
        "candidate_activity_scope_ids": template.candidate_activity_scope_ids or [],
        "observed_fact_templates": template.observed_fact_templates or [],
        "desired_fact_templates": template.desired_fact_templates or [],
    }


async def solve_maintenance(
    request: MaintenanceSolveRequest,
    session: AsyncSession,
) -> dict[str, Any]:
    """Merge multiple maintenance intents into one layered solve."""

    if not request.intent_template_ids:
        return _error_payload("NO_MAINTENANCE_INTENTS", "Maintenance solve requires at least one intent template")

    machine = await session.get(Machine, request.machine_id)
    if machine is None:
        return _error_payload("MACHINE_NOT_FOUND", f"Machine {request.machine_id} not found")

    current_state = await session.get(MachineState, request.current_state_id)
    if current_state is None or current_state.machine_id != request.machine_id:
        return _error_payload(
            "CURRENT_STATE_INVALID",
            f"Current state {request.current_state_id} does not belong to machine {request.machine_id}",
        )

    template_ids = _unique_ints(request.intent_template_ids)
    result = await session.execute(
        select(MaintenanceIntentTemplate)
        .where(MaintenanceIntentTemplate.id.in_(template_ids))
    )
    templates_by_id = {item.id: item for item in result.scalars().all()}
    missing_ids = [template_id for template_id in template_ids if template_id not in templates_by_id]
    if missing_ids:
        return _error_payload(
            "MAINTENANCE_INTENT_NOT_FOUND",
            "One or more maintenance intent templates were not found",
            {"missing_template_ids": missing_ids},
        )

    templates = [templates_by_id[template_id] for template_id in template_ids]
    wrong_machine_type = [
        template.id for template in templates if template.machine_type_id != machine.machine_type_id
    ]
    if wrong_machine_type:
        return _error_payload(
            "MAINTENANCE_INTENT_MACHINE_TYPE_MISMATCH",
            "Maintenance intent templates must belong to the machine type of the selected machine",
            {"template_ids": wrong_machine_type, "machine_type_id": machine.machine_type_id},
        )

    inactive_ids = [template.id for template in templates if not template.is_active]
    if inactive_ids and not request.include_inactive:
        return _error_payload(
            "INACTIVE_MAINTENANCE_INTENT",
            "Inactive maintenance intent templates require include_inactive=true",
            {"template_ids": inactive_ids},
        )

    valid_feature_keys = await _load_feature_keys(session, machine.machine_type_id)
    observed_facts = [
        _fact_from_json(fact)
        for template in templates
        for fact in (template.observed_fact_templates or [])
    ]
    observed_facts.extend(request.extra_observed_facts)
    desired_facts = [
        _fact_from_json(fact)
        for template in templates
        for fact in (template.desired_fact_templates or [])
    ]
    desired_facts.extend(request.extra_desired_facts)

    current_state_overrides, observed_conflicts = _merge_observed_facts(
        observed_facts,
        valid_feature_keys=valid_feature_keys,
    )
    direct_goal_facts, desired_conflicts = _merge_desired_facts(
        desired_facts,
        valid_feature_keys=valid_feature_keys,
    )
    if observed_conflicts or desired_conflicts:
        return _error_payload(
            "INVALID_MAINTENANCE_FACTS",
            "Maintenance facts cannot be merged into a solve request",
            {"observed_conflicts": observed_conflicts, "desired_conflicts": desired_conflicts},
        )

    target_state_node_ids = _unique_ints([
        state_node_id
        for template in templates
        for state_node_id in (template.target_state_node_ids or [])
    ])
    activity_scope_node_ids = _unique_ints([
        activity_node_id
        for template in templates
        for activity_node_id in (
            template.candidate_activity_scope_ids or [template.scope_activity_node_id]
        )
    ])

    if not target_state_node_ids and not direct_goal_facts:
        return _error_payload(
            "NO_MAINTENANCE_GOALS",
            "Maintenance solve requires at least one target state node or desired fact",
        )

    intent_summaries = [_template_summary(template) for template in templates]
    layered_request = LayeredSolveRequest(
        machine_id=request.machine_id,
        current_state_id=request.current_state_id,
        target_state_node_ids=target_state_node_ids,
        activity_scope_node_ids=activity_scope_node_ids,
        include_inactive=request.include_inactive,
        objective=request.objective,
        objectives=request.objectives,
        constraints=request.constraints,
        parent_plan_id=request.parent_plan_id,
        blockage_constraints=request.blockage_constraints,
        current_state_overrides=current_state_overrides,
        direct_goal_facts=direct_goal_facts,
        context={
            "mode": "maintenance",
            "intent_template_ids": template_ids,
            "intent_templates": intent_summaries,
        },
    )

    solve_result = await solve_layered(layered_request, session)
    solve_result["maintenance"] = {
        "intent_templates": intent_summaries,
        "target_state_node_ids": target_state_node_ids,
        "activity_scope_node_ids": activity_scope_node_ids,
        "current_state_overrides": current_state_overrides,
        "direct_goal_facts": [fact.model_dump(mode="json") for fact in direct_goal_facts],
        "merged_intent_count": len(templates),
    }
    return solve_result
