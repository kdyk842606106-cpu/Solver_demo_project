"""Prepare and materialize scheduling-rule snapshots and post-solve overrides."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.scheduler.rules import (
    SchedulingRuleError,
    builtin_scheduling_rules,
    scheduling_rule_supported_in_mode,
    validate_scheduling_config,
)
from app.db.models import CandidatePlan, CandidatePlanStep, Machine, OpRule


async def prepare_scheduling_rule_constraints(
    *,
    machine_id: int,
    parent_plan_id: int | None,
    constraints: dict[str, Any] | None,
    session: AsyncSession,
    solve_mode: str | None = None,
) -> dict[str, Any] | None:
    payload = deepcopy(constraints or {})
    requested = dict(payload.get("scheduling_rules") or {})
    new_override = requested.get("new_override")
    if new_override and parent_plan_id is None:
        raise SchedulingRuleError(
            "SCHEDULING_RULE_OVERRIDE_INITIAL_SOLVE_FORBIDDEN",
            "Scheduling rule exceptions require a parent plan",
        )

    inherited: dict[str, Any] = {}
    if parent_plan_id is not None:
        parent = await session.scalar(
            select(CandidatePlan)
            .where(CandidatePlan.id == parent_plan_id)
            .options(selectinload(CandidatePlan.solve_request))
        )
        if parent is None or parent.solve_request is None:
            raise SchedulingRuleError("SCHEDULING_RULE_OVERRIDE_INVALID", "Parent plan is unavailable")
        inherited = deepcopy((parent.solve_request.constraints or {}).get("scheduling_rules") or {})
        snapshot = inherited.get("snapshot") or []
        active_rule_codes = inherited.get("active_rule_codes")
    else:
        machine = await session.scalar(
            select(Machine).where(Machine.id == machine_id).options(selectinload(Machine.machine_type))
        )
        if machine is None or machine.machine_type is None:
            raise SchedulingRuleError("SCHEDULING_RULE_CONFIG_INVALID", "Machine type is unavailable")
        config = validate_scheduling_config(machine.machine_type.scheduling_config) or {"rules": []}
        snapshot = [
            rule
            for rule in config.get("rules") or []
            if scheduling_rule_supported_in_mode(rule, solve_mode)
        ]
        configured_codes = {rule["code"] for rule in snapshot}
        configured_types = {rule["type"] for rule in snapshot}
        snapshot.extend(
            rule
            for rule in builtin_scheduling_rules(solve_mode)
            if rule["code"] not in configured_codes
            and rule["type"] not in configured_types
        )
        active_rule_codes = requested.get("active_rule_codes")

    rule_by_code = {rule["code"]: rule for rule in snapshot}
    if active_rule_codes is None:
        active_rule_codes = [
            rule["code"] for rule in snapshot
            if rule.get("enabled", True) and rule.get("activation_mode", "default_on") in {"required", "default_on"}
        ]
    active_codes = {str(code) for code in active_rule_codes}
    active_codes.update(
        rule["code"] for rule in snapshot
        if rule.get("enabled", True) and rule.get("activation_mode") == "required"
    )
    unknown = active_codes - set(rule_by_code)
    if unknown:
        raise SchedulingRuleError("SCHEDULING_RULE_CONFIG_INVALID", f"Unknown active rules: {sorted(unknown)}")

    carried: list[dict[str, Any]] = []
    carry_keys = {str(key) for key in requested.get("carry_parent_override_keys") or []}
    for override in inherited.get("overrides") or []:
        if str(override.get("override_key")) in carry_keys:
            carried.append(deepcopy(override))

    if new_override:
        override = dict(new_override)
        reason = str(override.get("reason") or "").strip()
        source_step_id = override.get("source_step_id")
        rule_code = str(override.get("rule_code") or "")
        if not reason or source_step_id is None or rule_code not in rule_by_code:
            raise SchedulingRuleError(
                "SCHEDULING_RULE_OVERRIDE_INVALID",
                "Rule exception requires rule_code, source_step_id and reason",
            )
        rule = rule_by_code[rule_code]
        if not (rule.get("enforcement") or {}).get("overridable"):
            raise SchedulingRuleError("SCHEDULING_RULE_OVERRIDE_NOT_ALLOWED", f"Rule {rule_code} is not overridable")
        carried.append({
            "override_key": str(uuid4()),
            "rule_code": rule_code,
            "source_step_id": int(source_step_id),
            "parameters": dict(override.get("parameters") or {}),
            "reason": reason,
        })

    payload["scheduling_rules"] = {
        "active_rule_codes": sorted(active_codes),
        "snapshot": snapshot,
        "overrides": carried,
    }
    return payload


async def materialize_scheduling_rule_overrides(
    constraints: dict[str, Any] | None,
    *,
    candidate_plan_id: int,
    session: AsyncSession,
) -> dict[str, Any] | None:
    payload = deepcopy(constraints or {})
    context = dict(payload.get("scheduling_rules") or {})
    materialized = []
    for override in context.get("overrides") or []:
        source_step_id = override.get("source_step_id")
        source = await session.get(CandidatePlanStep, source_step_id) if source_step_id is not None else None
        if source is None:
            raise SchedulingRuleError("SCHEDULING_RULE_OVERRIDE_INVALID", "Exception source step is unavailable")
        target = await session.scalar(
            select(CandidatePlanStep).where(
                CandidatePlanStep.candidate_plan_id == candidate_plan_id,
                CandidatePlanStep.step_order == source.step_order,
            )
        )
        if target is None:
            raise SchedulingRuleError("SCHEDULING_RULE_OVERRIDE_INVALID", "Exception target step is unavailable")
        item = dict(override)
        item["source_step_id"] = target.id
        item["target_step_order"] = target.step_order
        materialized.append(item)
    context["overrides"] = materialized
    payload["scheduling_rules"] = context
    return payload


async def scheduling_rule_exception_candidates(
    constraints: dict[str, Any] | None,
    *,
    candidate_plan_id: int,
    diagnostics: dict[str, Any] | None,
    session: AsyncSession,
) -> list[dict[str, Any]]:
    """Describe concrete failed-plan tasks that may receive a post-solve exception."""
    context = dict((constraints or {}).get("scheduling_rules") or {})
    active = {str(code) for code in context.get("active_rule_codes") or []}
    overridable = {
        rule["code"]: rule
        for rule in context.get("snapshot") or []
        if rule.get("code") in active and (rule.get("enforcement") or {}).get("overridable")
    }
    matched = ((diagnostics or {}).get("scheduling_rules") or {}).get("matched_rule_codes_by_step") or {}
    if not overridable or not matched:
        return []
    rows = await session.execute(
        select(
            CandidatePlanStep.id,
            CandidatePlanStep.step_order,
            OpRule.code,
            OpRule.name,
        )
        .join(OpRule, OpRule.id == CandidatePlanStep.op_rule_id)
        .where(CandidatePlanStep.candidate_plan_id == candidate_plan_id)
        .order_by(CandidatePlanStep.step_order)
    )
    candidates = []
    for step_id, step_order, op_rule_code, op_rule_name in rows.all():
        rule_codes = [
            code for code in matched.get(str(step_order), matched.get(step_order, []))
            if code in overridable
        ]
        if rule_codes:
            candidates.append({
                "step_id": step_id,
                "step_order": step_order,
                "op_rule_code": op_rule_code,
                "op_rule_name": op_rule_name,
                "matched_scheduling_rules": rule_codes,
                "overridable_rules": [overridable[code] for code in rule_codes],
            })
    return candidates
