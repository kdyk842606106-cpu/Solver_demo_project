"""Application-layer validation and discovery for machine scheduling rules."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.scheduler.rules import (
    SchedulingRuleError,
    scheduling_rule_type_descriptors,
    validate_scheduling_config,
)
from app.db.models import (
    AtomicActivity,
    MachineType,
    OpRule,
    OpRuleResourceReq,
    StateFeatureDef,
    WorkCalendarRevision,
)


async def validate_scheduling_config_references(
    machine_type_id: int,
    config: dict[str, Any] | None,
    session: AsyncSession,
) -> None:
    rules = (config or {}).get("rules") or []
    requested_dimensions = {
        str(key)
        for rule in rules
        for key in (rule.get("selector") or {}).get("effect_dimension_keys") or []
    }
    if requested_dimensions:
        known_dimensions = set((await session.scalars(
            select(StateFeatureDef.feature_key).where(
                StateFeatureDef.machine_type_id == machine_type_id,
                StateFeatureDef.is_dimension_template.is_(True),
            )
        )).all())
        missing = requested_dimensions - known_dimensions
        if missing:
            raise SchedulingRuleError(
                "SCHEDULING_RULE_REFERENCE_INVALID",
                f"Unknown state dimension templates: {sorted(missing)}",
            )

    requested_resources = {
        str((rule.get("selector") or {}).get("required_resource_type"))
        for rule in rules
        if (rule.get("selector") or {}).get("required_resource_type")
    }
    if requested_resources:
        known_resources = set((await session.scalars(
            select(OpRuleResourceReq.resource_type)
            .join(OpRule, OpRule.id == OpRuleResourceReq.op_rule_id)
            .where(OpRule.machine_type_id == machine_type_id)
            .distinct()
        )).all())
        missing = requested_resources - known_resources
        if missing:
            raise SchedulingRuleError(
                "SCHEDULING_RULE_REFERENCE_INVALID",
                f"Unknown operation resource types: {sorted(missing)}",
            )

    requested_shifts = {
        str(code)
        for rule in rules if rule.get("type") == "shift_restriction"
        for code in (rule.get("parameters") or {}).get("allowed_shift_codes") or []
    }
    if requested_shifts:
        revisions = (await session.scalars(select(WorkCalendarRevision))).all()
        known_shifts = {
            str(window.get("shift_code"))
            for revision in revisions
            for window in [
                *(revision.weekly_windows or []),
                *(
                    nested
                    for exception in revision.date_exceptions or []
                    for nested in exception.get("windows") or []
                ),
            ]
            if window.get("shift_code")
        }
        missing = requested_shifts - known_shifts
        if missing:
            raise SchedulingRuleError(
                "SCHEDULING_RULE_REFERENCE_INVALID",
                f"Unknown shift codes: {sorted(missing)}",
            )


def _validation_issue(
    code: str,
    severity: str,
    message: str,
    *,
    rule_code: str | None = None,
    related_activity_ids: list[str] | None = None,
    details: dict[str, Any] | None = None,
    suggested_action: str | None = None,
) -> dict[str, Any]:
    issue_details = dict(details or {})
    if rule_code is not None:
        issue_details["rule_code"] = rule_code
    return {
        "id": f"scheduling_rule:{code}:{rule_code or '-'}:{','.join(related_activity_ids or [])}",
        "code": code,
        "severity": severity,
        "category": "scheduling_rule",
        "message": message,
        "related_state_ids": [],
        "related_activity_ids": related_activity_ids or [],
        "details": issue_details or None,
        "suggested_action": suggested_action,
    }


def _effect_dimensions(
    op_rule: OpRule,
    feature_by_key: dict[str, StateFeatureDef],
    feature_by_id: dict[int, StateFeatureDef],
) -> set[str]:
    result: set[str] = set()
    for effect in op_rule.effects:
        feature = feature_by_key.get(effect.feature_key)
        if feature is None:
            continue
        template = (
            feature
            if feature.is_dimension_template
            else feature_by_id.get(feature.dimension_template_id)
        )
        if template is not None:
            result.add(template.feature_key)
    return result


def _rule_matches_operation(
    op_rule: OpRule,
    selector: dict[str, Any],
    feature_by_key: dict[str, StateFeatureDef],
    feature_by_id: dict[int, StateFeatureDef],
) -> bool:
    if selector.get("match") == "all":
        return True
    requested_resource = selector.get("required_resource_type")
    if requested_resource is not None and not any(
        req.is_required and req.resource_type == requested_resource
        for req in op_rule.resource_reqs
    ):
        return False
    requested_dimensions = {
        str(key) for key in selector.get("effect_dimension_keys") or []
    }
    if requested_dimensions and not requested_dimensions.intersection(
        _effect_dimensions(op_rule, feature_by_key, feature_by_id)
    ):
        return False
    requested_subsystem = selector.get("responsible_subsystem")
    if requested_subsystem is not None:
        metadata = (
            op_rule.atomic_activity.metadata_json
            if op_rule.atomic_activity is not None
            and isinstance(op_rule.atomic_activity.metadata_json, dict)
            else {}
        )
        if metadata.get("responsible_subsystem") != requested_subsystem:
            return False
    return True


async def validate_machine_type_scheduling_rules(
    machine_type_id: int,
    session: AsyncSession,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return scheduling-rule issues for the existing unified validation check."""

    machine_type = await session.get(MachineType, machine_type_id)
    if machine_type is None or machine_type.scheduling_config is None:
        return [], []
    try:
        config = validate_scheduling_config(machine_type.scheduling_config) or {
            "responsible_subsystems": [],
            "rules": [],
        }
    except SchedulingRuleError as exc:
        return [], [
            _validation_issue(
                exc.code,
                "error",
                str(exc),
                details={"machine_type_id": machine_type_id},
                suggested_action="在活动能力的机器类型排期设置中修正规则类型、启用方式和参数。",
            )
        ]

    modeling_issues: list[dict[str, Any]] = []
    solver_ready_issues: list[dict[str, Any]] = []
    configured_subsystems = {
        str(item["code"]) for item in config.get("responsible_subsystems") or []
    }
    atomic_activities = list((await session.scalars(
        select(AtomicActivity).where(AtomicActivity.machine_type_id == machine_type_id)
    )).all())
    for activity in atomic_activities:
        metadata = activity.metadata_json if isinstance(activity.metadata_json, dict) else {}
        subsystem = str(metadata.get("responsible_subsystem") or "").strip()
        if subsystem and subsystem not in configured_subsystems:
            solver_ready_issues.append(
                _validation_issue(
                    "RESPONSIBLE_SUBSYSTEM_INVALID",
                    "error",
                    f"原子活动 {activity.name} 引用了已不存在的责任子系统 {subsystem}。",
                    related_activity_ids=[f"atomic_activity:{activity.id}"],
                    details={
                        "atomic_activity_id": activity.id,
                        "responsible_subsystem": subsystem,
                    },
                    suggested_action="恢复该责任子系统选项，或为原子活动重新选择有效责任子系统。",
                )
            )

    feature_defs = list((await session.scalars(
        select(StateFeatureDef).where(StateFeatureDef.machine_type_id == machine_type_id)
    )).all())
    feature_by_key = {item.feature_key: item for item in feature_defs}
    feature_by_id = {item.id: item for item in feature_defs}
    known_dimensions = {
        item.feature_key for item in feature_defs if item.is_dimension_template
    }
    revisions = list((await session.scalars(select(WorkCalendarRevision))).all())
    known_shifts = {
        str(window.get("shift_code"))
        for revision in revisions
        for window in [
            *(revision.weekly_windows or []),
            *(
                nested
                for exception in revision.date_exceptions or []
                for nested in exception.get("windows") or []
            ),
        ]
        if window.get("shift_code")
    }
    op_rules = list((await session.scalars(
        select(OpRule)
        .where(OpRule.machine_type_id == machine_type_id, OpRule.is_active.is_(True))
        .options(
            selectinload(OpRule.resource_reqs),
            selectinload(OpRule.effects),
            selectinload(OpRule.atomic_activity),
        )
    )).all())
    known_resources = {
        req.resource_type
        for op_rule in op_rules
        for req in op_rule.resource_reqs
        if req.is_required
    }

    for rule in config.get("rules") or []:
        rule_code = str(rule["code"])
        selector = rule.get("selector") or {}
        requested_dimensions = {
            str(key) for key in selector.get("effect_dimension_keys") or []
        }
        missing_dimensions = sorted(requested_dimensions - known_dimensions)
        if missing_dimensions:
            solver_ready_issues.append(
                _validation_issue(
                    "SCHEDULING_RULE_DIMENSION_REFERENCE_INVALID",
                    "error",
                    f"规则 {rule_code} 引用了不存在的状态维度模板。",
                    rule_code=rule_code,
                    details={"missing_dimension_keys": missing_dimensions},
                    suggested_action="在状态维度中恢复模板，或修改规则选择器。",
                )
            )

        requested_resource = selector.get("required_resource_type")
        if requested_resource and requested_resource not in known_resources:
            solver_ready_issues.append(
                _validation_issue(
                    "SCHEDULING_RULE_RESOURCE_REFERENCE_INVALID",
                    "error",
                    f"规则 {rule_code} 引用了没有活动使用的资源类型 {requested_resource}。",
                    rule_code=rule_code,
                    details={"resource_type": requested_resource},
                    suggested_action="为工序配置该资源需求，或修改规则选择器。",
                )
            )

        allowed_shifts = {
            str(code) for code in (rule.get("parameters") or {}).get("allowed_shift_codes") or []
        }
        missing_shifts = sorted(allowed_shifts - known_shifts)
        if missing_shifts:
            solver_ready_issues.append(
                _validation_issue(
                    "SCHEDULING_RULE_SHIFT_REFERENCE_INVALID",
                    "error",
                    f"规则 {rule_code} 引用了不存在的 shift code。",
                    rule_code=rule_code,
                    details={"missing_shift_codes": missing_shifts},
                    suggested_action="在工作日历中恢复班次编码，或修改规则允许班次。",
                )
            )

        matched = [
            op_rule for op_rule in op_rules
            if _rule_matches_operation(op_rule, selector, feature_by_key, feature_by_id)
        ]
        if rule.get("enabled", True) and not matched:
            modeling_issues.append(
                _validation_issue(
                    "SCHEDULING_RULE_NO_MATCH",
                    "warning",
                    f"规则 {rule_code} 当前未匹配任何启用的可执行活动。",
                    rule_code=rule_code,
                    suggested_action="检查规则选择器，或补齐对应活动的资源、效果维度或责任子系统。",
                )
            )

    return modeling_issues, solver_ready_issues


__all__ = [
    "SchedulingRuleError",
    "scheduling_rule_type_descriptors",
    "validate_machine_type_scheduling_rules",
    "validate_scheduling_config",
    "validate_scheduling_config_references",
]
