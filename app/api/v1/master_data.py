"""
Master data CRUD endpoints.

These endpoints support the user-facing data management flow:
- machines and machine types
- state feature definitions
- machine states
- operation rules
- resources

The planner/scheduler pipeline continues to read the same underlying tables.
"""

import re
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import Select, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    ActivityPackageAtomicRef,
    ActivityNode,
    AtomicActivity,
    CandidatePlanStep,
    FeatureDefinition,
    Machine,
    MachineState,
    MachineStateFeature,
    MachineType,
    MaintenanceIntentTemplate,
    OpRule,
    OpRuleEffect,
    OpRulePrecond,
    OpRuleResourceReq,
    Resource,
    ScopeGuard,
    ScopeGuardPrecond,
    SolveRequest,
    StateFeatureDef,
    StateNode,
)
from app.db.schemas import (
    ActivityPackageAtomicRefCreate,
    ActivityPackageAtomicRefResponse,
    ActivityNodeCreate,
    ActivityNodeResponse,
    ActivityNodeUpdate,
    AtomicActivityCreate,
    AtomicActivityResponse,
    AtomicActivityUpdate,
    MachineCreate,
    MachineDetailResponse,
    MachineResponse,
    MachineStateCreate,
    MachineStateDetailResponse,
    MachineStateUpdate,
    MachineTypeCreate,
    MachineTypeDetailResponse,
    MachineTypeResponse,
    MachineTypeUpdate,
    MaintenanceIntentTemplateCreate,
    MaintenanceIntentTemplateResponse,
    MaintenanceIntentTemplateUpdate,
    OpRuleCreate,
    OpRuleDetailResponse,
    OpRuleUpdate,
    ResourceCreate,
    ResourceResponse,
    ResourceUpdate,
    ScopeGuardCreate,
    ScopeGuardResponse,
    ScopeGuardUpdate,
    StateFeatureDefCreate,
    StateFeatureDefResponse,
    StateFeatureDefUpdate,
    StateNodeCreate,
    StateNodeResponse,
    StateNodeUpdate,
    FeatureDefinitionCreate,
    FeatureDefinitionResponse,
    LayeredExpansionRequest,
    LayeredExpansionResponse,
    LayeredHealthCheckResponse,
)
from app.db.session import get_db_session
from app.services.layered_expansion import expand_layered_context
from app.services.layered_health import check_layered_health

router = APIRouter(tags=["master-data"])


def _extract_allowed_values(payload: Any) -> Optional[set[str]]:
    """Accept both list and legacy dict shapes for enum values."""
    if not payload:
        return None

    if isinstance(payload, list):
        return {str(item) for item in payload} if payload else None

    if isinstance(payload, dict):
        candidates = None
        for key in ("values", "options", "allowed_values", "items"):
            if isinstance(payload.get(key), list):
                candidates = payload[key]
                break
        if candidates is None and all(isinstance(k, str) for k in payload.keys()):
            candidates = list(payload.keys())
        if not candidates:
            return None
        return {str(item) for item in candidates}

    return None


def _normalize_allowed_values(payload: Any) -> Optional[list[Any]]:
    """Return allowed_values as a list regardless of stored format."""
    if payload is None:
        return None
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        # Legacy format: {"values": [...]} → unwrap to plain list
        return payload.get("values", list(payload.values()))
    return [payload]


def _serialize_feature_def(feature_def: StateFeatureDef) -> dict[str, Any]:
    return {
        "id": feature_def.id,
        "machine_type_id": feature_def.machine_type_id,
        "feature_key": feature_def.feature_key,
        "feature_name": feature_def.feature_name,
        "value_type": feature_def.value_type,
        "allowed_values": _normalize_allowed_values(feature_def.allowed_values),
    }


async def _get_machine_type_or_404(machine_type_id: int, session: AsyncSession) -> MachineType:
    obj = await session.get(MachineType, machine_type_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Machine type {machine_type_id} not found")
    return obj


async def _get_machine_or_404(machine_id: int, session: AsyncSession) -> Machine:
    obj = await session.get(Machine, machine_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Machine {machine_id} not found")
    return obj


async def _get_state_or_404(state_id: int, session: AsyncSession) -> MachineState:
    result = await session.execute(
        select(MachineState)
        .where(MachineState.id == state_id)
        .options(selectinload(MachineState.features))
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"State {state_id} not found")
    return obj


async def _get_rule_or_404(rule_id: int, session: AsyncSession) -> OpRule:
    result = await session.execute(
        select(OpRule)
        .where(OpRule.id == rule_id)
        .options(
            selectinload(OpRule.preconditions),
            selectinload(OpRule.effects),
            selectinload(OpRule.resource_reqs),
            selectinload(OpRule.atomic_activity),
        )
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Op rule {rule_id} not found")
    return obj


async def _get_feature_def_or_404(feature_def_id: int, session: AsyncSession) -> StateFeatureDef:
    obj = await session.get(StateFeatureDef, feature_def_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Feature definition {feature_def_id} not found")
    return obj


async def _get_resource_or_404(resource_id: int, session: AsyncSession) -> Resource:
    obj = await session.get(Resource, resource_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Resource {resource_id} not found")
    return obj


async def _ensure_resource_code_unique(
    session: AsyncSession,
    machine_id: int,
    code: str,
    exclude_id: Optional[int] = None,
) -> None:
    query = select(Resource.id).where(Resource.machine_id == machine_id, Resource.code == code)
    if exclude_id is not None:
        query = query.where(Resource.id != exclude_id)
    result = await session.execute(query.limit(1))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Resource code '{code}' already exists for machine {machine_id}",
        )


async def _get_activity_node_or_404(node_id: int, session: AsyncSession) -> ActivityNode:
    result = await session.execute(
        select(ActivityNode)
        .where(ActivityNode.id == node_id)
        .options(
            selectinload(ActivityNode.children),
            selectinload(ActivityNode.op_rules),
            selectinload(ActivityNode.scope_guards),
        )
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Activity node {node_id} not found")
    return obj


async def _get_atomic_activity_or_404(atomic_activity_id: int, session: AsyncSession) -> AtomicActivity:
    result = await session.execute(
        select(AtomicActivity)
        .where(AtomicActivity.id == atomic_activity_id)
        .options(
            selectinload(AtomicActivity.package_refs).selectinload(ActivityPackageAtomicRef.activity_node),
            selectinload(AtomicActivity.op_rules),
        )
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Atomic activity {atomic_activity_id} not found")
    return obj


async def _get_atomic_ref_or_404(ref_id: int, session: AsyncSession) -> ActivityPackageAtomicRef:
    result = await session.execute(
        select(ActivityPackageAtomicRef)
        .where(ActivityPackageAtomicRef.id == ref_id)
        .options(
            selectinload(ActivityPackageAtomicRef.activity_node),
            selectinload(ActivityPackageAtomicRef.atomic_activity),
        )
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Atomic activity reference {ref_id} not found")
    return obj


async def _get_state_node_or_404(node_id: int, session: AsyncSession) -> StateNode:
    result = await session.execute(
        select(StateNode)
        .where(StateNode.id == node_id)
        .options(
            selectinload(StateNode.children),
            selectinload(StateNode.scope_guard_preconditions),
        )
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"State node {node_id} not found")
    return obj


async def _get_scope_guard_or_404(guard_id: int, session: AsyncSession) -> ScopeGuard:
    result = await session.execute(
        select(ScopeGuard)
        .where(ScopeGuard.id == guard_id)
        .options(
            selectinload(ScopeGuard.activity_node),
            selectinload(ScopeGuard.preconditions).selectinload(ScopeGuardPrecond.state_node),
        )
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Scope Guard {guard_id} not found")
    return obj


async def _get_maintenance_intent_template_or_404(
    template_id: int,
    session: AsyncSession,
) -> MaintenanceIntentTemplate:
    obj = await session.get(MaintenanceIntentTemplate, template_id)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Maintenance intent template {template_id} not found")
    return obj


async def _ensure_unique(
    session: AsyncSession,
    model: type,
    field_name: str,
    value: str,
    *,
    exclude_id: Optional[int] = None,
) -> None:
    column = getattr(model, field_name)
    query = select(model.id).where(column == value)
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)

    existing = await session.execute(query.limit(1))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"{model.__name__} with {field_name}={value} already exists")


async def _ensure_node_code_unique(
    session: AsyncSession,
    model: type[ActivityNode] | type[StateNode],
    machine_type_id: int,
    code: str,
    *,
    exclude_id: Optional[int] = None,
) -> None:
    query = select(model.id).where(model.machine_type_id == machine_type_id, model.code == code)
    if exclude_id is not None:
        query = query.where(model.id != exclude_id)
    existing = await session.execute(query.limit(1))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Node code '{code}' already exists for this machine type")


async def _ensure_atomic_code_unique(
    session: AsyncSession,
    machine_type_id: int,
    code: str,
    *,
    exclude_id: Optional[int] = None,
) -> None:
    query = select(AtomicActivity.id).where(
        AtomicActivity.machine_type_id == machine_type_id,
        AtomicActivity.code == code,
    )
    if exclude_id is not None:
        query = query.where(AtomicActivity.id != exclude_id)
    existing = await session.execute(query.limit(1))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Atomic activity code '{code}' already exists for this machine type")


def _normalize_code_token(value: Optional[str], fallback: str) -> str:
    token = re.sub(r"[^0-9a-z]+", "_", (value or "").strip().lower())
    token = re.sub(r"_+", "_", token).strip("_")
    return token or fallback


def _auto_code_prefix(machine_type: MachineType, suffix: str) -> str:
    base = _normalize_code_token(machine_type.code, f"mt{machine_type.id}")
    suffix = _normalize_code_token(suffix, "node")
    max_base_len = max(1, 64 - len(suffix) - len("__0001"))
    base = base[:max_base_len].strip("_") or f"mt{machine_type.id}"
    return f"{base}_{suffix}"


async def _generate_machine_type_code(
    session: AsyncSession,
    model: type[ActivityNode] | type[StateNode] | type[AtomicActivity],
    machine_type: MachineType,
    suffix: str,
) -> str:
    prefix = _auto_code_prefix(machine_type, suffix)
    result = await session.execute(
        select(model.code).where(
            model.machine_type_id == machine_type.id,
            model.code.like(f"{prefix}_%"),
        )
    )
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    max_seq = 0
    for code in result.scalars().all():
        match = pattern.match(code or "")
        if match:
            max_seq = max(max_seq, int(match.group(1)))

    seq = max_seq + 1
    while True:
        candidate = f"{prefix}_{seq:04d}"
        exists = await session.execute(
            select(model.id).where(
                model.machine_type_id == machine_type.id,
                model.code == candidate,
            ).limit(1)
        )
        if exists.scalar_one_or_none() is None:
            return candidate
        seq += 1


async def _generate_op_rule_code(
    session: AsyncSession,
    machine_type: MachineType,
) -> str:
    prefix = _auto_code_prefix(machine_type, "or")
    result = await session.execute(select(OpRule.code).where(OpRule.code.like(f"{prefix}_%")))
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    max_seq = 0
    for code in result.scalars().all():
        match = pattern.match(code or "")
        if match:
            max_seq = max(max_seq, int(match.group(1)))

    seq = max_seq + 1
    while True:
        candidate = f"{prefix}_{seq:04d}"
        exists = await session.execute(select(OpRule.id).where(OpRule.code == candidate).limit(1))
        if exists.scalar_one_or_none() is None:
            return candidate
        seq += 1


def _clean_optional_code(value: Optional[str]) -> Optional[str]:
    code = (value or "").strip()
    return code or None


async def _validate_activity_parent(
    session: AsyncSession,
    machine_type_id: int,
    level: int,
    parent_id: Optional[int],
    *,
    current_id: Optional[int] = None,
) -> None:
    if level == 1:
        if parent_id is not None:
            raise HTTPException(status_code=422, detail="Level-1 activity nodes cannot have a parent")
        return
    if parent_id is None:
        raise HTTPException(status_code=422, detail="Level-2/3 activity nodes require a parent")
    if current_id is not None and parent_id == current_id:
        raise HTTPException(status_code=422, detail="Activity node cannot be its own parent")
    parent = await _get_activity_node_or_404(parent_id, session)
    if parent.machine_type_id != machine_type_id:
        raise HTTPException(status_code=422, detail="Activity parent must belong to the same machine type")
    if parent.level != level - 1:
        raise HTTPException(status_code=422, detail="Activity parent level must be exactly one level above child")


async def _validate_state_parent(
    session: AsyncSession,
    machine_type_id: int,
    level: int,
    parent_id: Optional[int],
    *,
    current_id: Optional[int] = None,
) -> None:
    if level == 1:
        if parent_id is not None:
            raise HTTPException(status_code=422, detail="Level-1 state nodes cannot have a parent")
        return
    if parent_id is None:
        raise HTTPException(status_code=422, detail="Non-root state nodes require a parent")
    if current_id is not None and parent_id == current_id:
        raise HTTPException(status_code=422, detail="State node cannot be its own parent")
    parent = await _get_state_node_or_404(parent_id, session)
    if parent.machine_type_id != machine_type_id:
        raise HTTPException(status_code=422, detail="State parent must belong to the same machine type")
    if parent.level != level - 1:
        raise HTTPException(status_code=422, detail="State parent level must be exactly one level above child")
    if parent.state_kind != "aggregate" or parent.feature_key or parent.target_value:
        raise HTTPException(status_code=422, detail="State parent must be an aggregate package before adding children")


def _append_allowed_value(allowed_values: Any, value: str) -> list[Any]:
    values = _normalize_allowed_values(allowed_values) or []
    text_values = {str(item) for item in values}
    if value not in text_values:
        values.append(value)
    return values


async def _ensure_state_feature_def_for_leaf(
    session: AsyncSession,
    machine_type_id: int,
    *,
    feature_key: str,
    feature_name: str,
    target_value: str,
) -> None:
    global_def = await session.get(FeatureDefinition, feature_key)
    if global_def is None:
        session.add(
            FeatureDefinition(
                feature_key=feature_key,
                value_type="enum",
                allowed_values=[target_value],
                description=f"Auto-created from state leaf '{feature_name}'",
            )
        )
    elif global_def.value_type == "enum":
        global_def.allowed_values = _append_allowed_value(global_def.allowed_values, target_value)

    result = await session.execute(
        select(StateFeatureDef).where(
            StateFeatureDef.machine_type_id == machine_type_id,
            StateFeatureDef.feature_key == feature_key,
        )
    )
    feature_def = result.scalar_one_or_none()
    if feature_def is None:
        session.add(
            StateFeatureDef(
                machine_type_id=machine_type_id,
                feature_key=feature_key,
                feature_name=feature_name,
                value_type="enum",
                allowed_values=[target_value],
            )
        )
    elif feature_def.value_type == "enum":
        feature_def.allowed_values = _append_allowed_value(feature_def.allowed_values, target_value)


async def _validate_state_node_payload(
    session: AsyncSession,
    machine_type_id: int,
    payload: StateNodeCreate | StateNodeUpdate,
    *,
    has_children: bool = False,
) -> None:
    if payload.state_kind == "aggregate" or has_children:
        if payload.state_kind != "aggregate":
            raise HTTPException(status_code=422, detail="State nodes with children must be aggregate states")
        if payload.feature_key or payload.target_value:
            raise HTTPException(status_code=422, detail="Aggregate state nodes cannot bind feature values")
        return

    if not payload.feature_key:
        raise HTTPException(status_code=422, detail="Atomic state nodes require a feature_key")
    if payload.operator != "eq":
        raise HTTPException(status_code=422, detail="Atomic state nodes currently support operator 'eq' only")
    if not payload.target_value:
        raise HTTPException(status_code=422, detail="Atomic state nodes require a target_value")

    await _ensure_state_feature_def_for_leaf(
        session,
        machine_type_id,
        feature_key=payload.feature_key,
        feature_name=payload.name,
        target_value=payload.target_value,
    )


async def _validate_activity_node_for_rule(
    session: AsyncSession,
    machine_type_id: int,
    activity_node_id: Optional[int],
) -> None:
    if activity_node_id is None:
        return
    node = await _get_activity_node_or_404(activity_node_id, session)
    if node.machine_type_id != machine_type_id:
        raise HTTPException(status_code=422, detail="Activity node must belong to the same machine type as the op rule")
    if node.level != 3:
        raise HTTPException(status_code=422, detail="Op rules can only bind to level-3 activity nodes")


async def _validate_atomic_activity_for_rule(
    session: AsyncSession,
    machine_type_id: int,
    atomic_activity_id: Optional[int],
) -> None:
    if atomic_activity_id is None:
        return
    activity = await _get_atomic_activity_or_404(atomic_activity_id, session)
    if activity.machine_type_id != machine_type_id:
        raise HTTPException(status_code=422, detail="Atomic activity must belong to the same machine type as the op rule")


async def _validate_activity_package_for_ref(
    session: AsyncSession,
    package_id: int,
) -> ActivityNode:
    package = await _get_activity_node_or_404(package_id, session)
    if package.level != 2:
        raise HTTPException(status_code=422, detail="Atomic activities can only be attached to level-2 activity packages")
    return package


def _serialize_activity_node(node: ActivityNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "machine_type_id": node.machine_type_id,
        "parent_id": node.parent_id,
        "level": node.level,
        "code": node.code,
        "name": node.name,
        "activity_category": node.activity_category,
        "sort_order": node.sort_order,
        "is_active": node.is_active,
        "metadata_json": node.metadata_json,
        "created_at": node.created_at,
    }


def _serialize_atomic_activity(activity: AtomicActivity) -> dict[str, Any]:
    return {
        "id": activity.id,
        "machine_type_id": activity.machine_type_id,
        "code": activity.code,
        "name": activity.name,
        "activity_category": activity.activity_category,
        "sort_order": activity.sort_order,
        "is_active": activity.is_active,
        "metadata_json": activity.metadata_json,
        "created_at": activity.created_at,
    }


def _serialize_atomic_ref(ref: ActivityPackageAtomicRef) -> dict[str, Any]:
    atomic = ref.atomic_activity
    return {
        "id": ref.id,
        "activity_node_id": ref.activity_node_id,
        "atomic_activity_id": ref.atomic_activity_id,
        "atomic_activity_code": atomic.code if atomic else None,
        "atomic_activity_name": atomic.name if atomic else None,
        "activity_category": atomic.activity_category if atomic else None,
        "sort_order": ref.sort_order,
        "is_active": ref.is_active,
        "metadata_json": ref.metadata_json,
        "created_at": ref.created_at,
    }


def _serialize_state_node(node: StateNode) -> dict[str, Any]:
    return {
        "id": node.id,
        "machine_type_id": node.machine_type_id,
        "parent_id": node.parent_id,
        "level": node.level,
        "code": node.code,
        "name": node.name,
        "feature_key": node.feature_key,
        "operator": node.operator,
        "target_value": node.target_value,
        "state_kind": node.state_kind,
        "sort_order": node.sort_order,
        "is_active": node.is_active,
        "metadata_json": node.metadata_json,
        "created_at": node.created_at,
    }


def _serialize_scope_guard(guard: ScopeGuard) -> dict[str, Any]:
    return {
        "id": guard.id,
        "activity_node_id": guard.activity_node_id,
        "name": guard.name,
        "description": guard.description,
        "is_active": guard.is_active,
        "metadata_json": guard.metadata_json,
        "created_at": guard.created_at,
        "preconditions": [
            {
                "id": item.id,
                "state_node_id": item.state_node_id,
                "state_node_code": item.state_node.code if item.state_node else None,
                "state_node_name": item.state_node.name if item.state_node else None,
                "state_node_level": item.state_node.level if item.state_node else None,
                "operator": item.operator,
                "expected_value": item.expected_value,
                "value_list": item.value_list,
            }
            for item in guard.preconditions
        ],
    }


def _serialize_maintenance_intent_template(template: MaintenanceIntentTemplate) -> dict[str, Any]:
    return {
        "id": template.id,
        "machine_type_id": template.machine_type_id,
        "scope_activity_node_id": template.scope_activity_node_id,
        "issue_type": template.issue_type,
        "name": template.name,
        "description": template.description,
        "target_state_node_ids": template.target_state_node_ids or [],
        "candidate_activity_scope_ids": template.candidate_activity_scope_ids or [],
        "observed_fact_templates": template.observed_fact_templates or [],
        "desired_fact_templates": template.desired_fact_templates or [],
        "is_active": template.is_active,
        "metadata_json": template.metadata_json,
        "created_at": template.created_at,
    }


async def _validate_maintenance_fact_templates(
    session: AsyncSession,
    machine_type_id: int,
    facts: list[Any],
    *,
    purpose: str,
) -> None:
    defs_result = await session.execute(
        select(StateFeatureDef.feature_key).where(StateFeatureDef.machine_type_id == machine_type_id)
    )
    valid_feature_keys = set(defs_result.scalars().all())
    for fact in facts:
        if fact.feature_key not in valid_feature_keys:
            raise HTTPException(
                status_code=422,
                detail=f"Feature key '{fact.feature_key}' is not defined for this machine type",
            )
        if fact.operator != "eq":
            raise HTTPException(
                status_code=422,
                detail=f"Maintenance {purpose} facts currently support operator 'eq' only",
            )
        if fact.value is None:
            raise HTTPException(
                status_code=422,
                detail=f"Maintenance {purpose} fact '{fact.feature_key}' requires a value",
            )


async def _validate_node_ids(
    session: AsyncSession,
    model: type[ActivityNode] | type[StateNode],
    machine_type_id: int,
    node_ids: list[int],
    *,
    label: str,
) -> None:
    if not node_ids:
        return
    unique_ids = sorted(set(node_ids))
    result = await session.execute(select(model).where(model.id.in_(unique_ids)))
    nodes = result.scalars().all()
    found_ids = {node.id for node in nodes}
    missing_ids = [node_id for node_id in unique_ids if node_id not in found_ids]
    if missing_ids:
        raise HTTPException(status_code=422, detail=f"{label} ids not found: {missing_ids}")
    wrong_machine_type = [node.id for node in nodes if node.machine_type_id != machine_type_id]
    if wrong_machine_type:
        raise HTTPException(
            status_code=422,
            detail=f"{label} ids must belong to machine type {machine_type_id}: {wrong_machine_type}",
        )


async def _ensure_maintenance_issue_unique(
    session: AsyncSession,
    machine_type_id: int,
    issue_type: str,
    *,
    exclude_id: Optional[int] = None,
) -> None:
    query = select(MaintenanceIntentTemplate.id).where(
        MaintenanceIntentTemplate.machine_type_id == machine_type_id,
        MaintenanceIntentTemplate.issue_type == issue_type,
    )
    if exclude_id is not None:
        query = query.where(MaintenanceIntentTemplate.id != exclude_id)
    existing = await session.execute(query.limit(1))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Maintenance issue_type '{issue_type}' already exists")


async def _validate_maintenance_template_payload(
    session: AsyncSession,
    machine_type_id: int,
    payload: MaintenanceIntentTemplateCreate | MaintenanceIntentTemplateUpdate,
    *,
    exclude_id: Optional[int] = None,
) -> list[int]:
    scope_node = await _get_activity_node_or_404(payload.scope_activity_node_id, session)
    if scope_node.machine_type_id != machine_type_id:
        raise HTTPException(status_code=422, detail="Maintenance scope activity must belong to the same machine type")
    if scope_node.level != 2:
        raise HTTPException(status_code=422, detail="Maintenance intent scope must be a level-2 activity node")

    await _ensure_maintenance_issue_unique(
        session,
        machine_type_id,
        payload.issue_type,
        exclude_id=exclude_id,
    )
    await _validate_node_ids(
        session,
        StateNode,
        machine_type_id,
        payload.target_state_node_ids,
        label="Target state node",
    )
    candidate_scope_ids = payload.candidate_activity_scope_ids or [payload.scope_activity_node_id]
    await _validate_node_ids(
        session,
        ActivityNode,
        machine_type_id,
        candidate_scope_ids,
        label="Candidate activity scope",
    )
    await _validate_maintenance_fact_templates(
        session,
        machine_type_id,
        payload.observed_fact_templates,
        purpose="observed",
    )
    await _validate_maintenance_fact_templates(
        session,
        machine_type_id,
        payload.desired_fact_templates,
        purpose="desired",
    )
    return list(dict.fromkeys(candidate_scope_ids))


async def _validate_state_features(
    session: AsyncSession,
    machine_type_id: int,
    features: dict[str, str],
) -> None:
    defs_result = await session.execute(
        select(StateFeatureDef).where(StateFeatureDef.machine_type_id == machine_type_id)
    )
    defs = defs_result.scalars().all()
    defs_by_key = {item.feature_key: item for item in defs}

    if not defs_by_key:
        raise HTTPException(status_code=422, detail="No feature definitions found for this machine type")

    for feature_key, feature_value in features.items():
        feature_def = defs_by_key.get(feature_key)
        if feature_def is None:
            raise HTTPException(
                status_code=422,
                detail=f"Feature key '{feature_key}' is not defined for machine type {machine_type_id}",
            )
        if feature_def.value_type == "enum":
            allowed_values = _extract_allowed_values(feature_def.allowed_values)
            if allowed_values and feature_value not in allowed_values:
                raise HTTPException(
                    status_code=422,
                    detail=f"Feature value '{feature_value}' is not allowed for '{feature_key}'",
                )


async def _validate_rule_features(
    session: AsyncSession,
    machine_type_id: int,
    preconditions: list[Any],
    effects: list[Any],
) -> None:
    defs_result = await session.execute(
        select(StateFeatureDef).where(StateFeatureDef.machine_type_id == machine_type_id)
    )
    defs = defs_result.scalars().all()
    valid_keys = {item.feature_key for item in defs}

    if not valid_keys:
        raise HTTPException(status_code=422, detail="No feature definitions found for this machine type")

    for item in preconditions:
        if item.feature_key not in valid_keys:
            raise HTTPException(
                status_code=422,
                detail=f"Precondition feature '{item.feature_key}' is not defined for machine type {machine_type_id}",
            )

    for item in effects:
        if item.feature_key not in valid_keys:
            raise HTTPException(
                status_code=422,
                detail=f"Effect feature '{item.feature_key}' is not defined for machine type {machine_type_id}",
            )


def _serialize_state(state: MachineState) -> dict[str, Any]:
    return {
        "state_id": state.id,
        "machine_id": state.machine_id,
        "state_type": state.state_type,
        "label": state.label,
        "created_at": state.created_at,
        "features": {feature.feature_key: feature.feature_value for feature in state.features},
    }


def _serialize_rule(rule: OpRule) -> dict[str, Any]:
    return {
        "id": rule.id,
        "machine_type_id": rule.machine_type_id,
        "activity_node_id": rule.activity_node_id,
        "atomic_activity_id": rule.atomic_activity_id,
        "code": rule.code,
        "name": rule.name,
        "duration_min": rule.duration_min,
        "description": rule.description,
        "is_active": rule.is_active,
        "is_repair": rule.is_repair,
        "valid_from": rule.valid_from,
        "valid_to": rule.valid_to,
        "created_at": rule.created_at,
        "preconditions": [
            {
                "id": item.id,
                "feature_key": item.feature_key,
                "operator": item.operator,
                "feature_value": item.feature_value,
                "value_list": item.value_list,
            }
            for item in rule.preconditions
        ],
        "effects": [
            {
                "id": item.id,
                "feature_key": item.feature_key,
                "new_value": item.new_value,
                "effect_type": item.effect_type,
                "delta_value": item.delta_value,
            }
            for item in rule.effects
        ],
        "resource_reqs": [
            {
                "id": item.id,
                "resource_type": item.resource_type,
                "quantity": item.quantity,
                "is_required": item.is_required,
            }
            for item in rule.resource_reqs
        ],
    }


async def _replace_state_features(
    state: MachineState,
    features: dict[str, str],
    session: AsyncSession,
) -> None:
    await session.execute(
        delete(MachineStateFeature).where(MachineStateFeature.machine_state_id == state.id)
    )
    session.add_all(
        [
            MachineStateFeature(
                machine_state_id=state.id,
                feature_key=feature_key,
                feature_value=feature_value,
            )
            for feature_key, feature_value in features.items()
        ]
    )


async def _replace_rule_children(
    rule: OpRule,
    payload: OpRuleCreate | OpRuleUpdate,
    session: AsyncSession,
) -> None:
    await session.execute(delete(OpRulePrecond).where(OpRulePrecond.op_rule_id == rule.id))
    await session.execute(delete(OpRuleEffect).where(OpRuleEffect.op_rule_id == rule.id))
    await session.execute(delete(OpRuleResourceReq).where(OpRuleResourceReq.op_rule_id == rule.id))

    session.add_all(
        [
            OpRulePrecond(
                op_rule_id=rule.id,
                feature_key=item.feature_key,
                operator=item.operator,
                feature_value=item.feature_value,
                value_list=item.value_list,
            )
            for item in payload.preconditions
        ]
    )
    session.add_all(
        [
            OpRuleEffect(
                op_rule_id=rule.id,
                feature_key=item.feature_key,
                new_value=item.new_value,
                effect_type=item.effect_type,
                delta_value=item.delta_value,
            )
            for item in payload.effects
        ]
    )
    session.add_all(
        [
            OpRuleResourceReq(
                op_rule_id=rule.id,
                resource_type=item.resource_type,
                quantity=item.quantity,
                is_required=item.is_required,
            )
            for item in payload.resource_reqs
        ]
    )


async def _validate_scope_guard_payload(
    session: AsyncSession,
    activity_node: ActivityNode,
    payload: ScopeGuardCreate | ScopeGuardUpdate,
) -> None:
    if activity_node.level not in (1, 2):
        raise HTTPException(status_code=422, detail="Scope Guards can only be attached to level-1 or level-2 activity nodes")
    if not payload.preconditions:
        raise HTTPException(status_code=422, detail="Scope Guard must contain at least one precondition")

    for item in payload.preconditions:
        state_node = await _get_state_node_or_404(item.state_node_id, session)
        if state_node.machine_type_id != activity_node.machine_type_id:
            raise HTTPException(status_code=422, detail="Scope Guard state references must belong to the same machine type")
        if activity_node.level == 1 and state_node.level != 1:
            raise HTTPException(status_code=422, detail="Level-1 activity Scope Guards can only reference level-1 state nodes")


async def _replace_scope_guard_preconditions(
    guard: ScopeGuard,
    payload: ScopeGuardCreate | ScopeGuardUpdate,
    session: AsyncSession,
) -> None:
    await session.execute(delete(ScopeGuardPrecond).where(ScopeGuardPrecond.scope_guard_id == guard.id))
    session.add_all(
        [
            ScopeGuardPrecond(
                scope_guard_id=guard.id,
                state_node_id=item.state_node_id,
                operator=item.operator,
                expected_value=item.expected_value,
                value_list=item.value_list,
            )
            for item in payload.preconditions
        ]
    )


@router.get("/machine-types", response_model=list[MachineTypeDetailResponse])
async def list_machine_types(db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(
        select(MachineType)
        .options(selectinload(MachineType.state_feature_defs))
        .order_by(MachineType.id)
    )
    items = result.scalars().all()
    return [
        {
            "id": item.id,
            "code": item.code,
            "name": item.name,
            "description": item.description,
            "created_at": item.created_at,
            "feature_defs": [_serialize_feature_def(feature_def) for feature_def in item.state_feature_defs],
        }
        for item in items
    ]


@router.post("/machine-types", response_model=MachineTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_machine_type(
    payload: MachineTypeCreate,
    db: AsyncSession = Depends(get_db_session),
):
    await _ensure_unique(db, MachineType, "code", payload.code)
    obj = MachineType(code=payload.code, name=payload.name, description=payload.description)
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


@router.put("/machine-types/{machine_type_id}", response_model=MachineTypeResponse)
async def update_machine_type(
    machine_type_id: int,
    payload: MachineTypeUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_machine_type_or_404(machine_type_id, db)
    await _ensure_unique(db, MachineType, "code", payload.code, exclude_id=machine_type_id)
    obj.code = payload.code
    obj.name = payload.name
    obj.description = payload.description
    await db.flush()
    await db.refresh(obj)
    return obj


@router.delete("/machine-types/{machine_type_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_machine_type(
    machine_type_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    result = await db.execute(
        select(MachineType)
        .where(MachineType.id == machine_type_id)
        .options(
            selectinload(MachineType.machines),
            selectinload(MachineType.state_feature_defs),
            selectinload(MachineType.op_rules),
        )
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Machine type {machine_type_id} not found")
    if obj.machines or obj.state_feature_defs or obj.op_rules:
        raise HTTPException(status_code=409, detail="Machine type is in use and cannot be deleted")
    await db.delete(obj)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/machine-types/{machine_type_id}/feature-defs", response_model=list[StateFeatureDefResponse])
async def list_feature_defs(machine_type_id: int, db: AsyncSession = Depends(get_db_session)):
    await _get_machine_type_or_404(machine_type_id, db)
    result = await db.execute(
        select(StateFeatureDef)
        .where(StateFeatureDef.machine_type_id == machine_type_id)
        .order_by(StateFeatureDef.id)
    )
    return [_serialize_feature_def(item) for item in result.scalars().all()]


@router.post(
    "/machine-types/{machine_type_id}/feature-defs",
    response_model=StateFeatureDefResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_feature_def(
    machine_type_id: int,
    payload: StateFeatureDefCreate,
    db: AsyncSession = Depends(get_db_session),
):
    await _get_machine_type_or_404(machine_type_id, db)
    existing = await db.execute(
        select(StateFeatureDef.id).where(
            StateFeatureDef.machine_type_id == machine_type_id,
            StateFeatureDef.feature_key == payload.feature_key,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Feature key '{payload.feature_key}' already exists")

    obj = StateFeatureDef(
        machine_type_id=machine_type_id,
        feature_key=payload.feature_key,
        feature_name=payload.feature_name,
        value_type=payload.value_type,
        allowed_values=payload.allowed_values,
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return _serialize_feature_def(obj)


@router.put("/feature-defs/{feature_def_id}", response_model=StateFeatureDefResponse)
async def update_feature_def(
    feature_def_id: int,
    payload: StateFeatureDefUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_feature_def_or_404(feature_def_id, db)
    existing = await db.execute(
        select(StateFeatureDef.id).where(
            StateFeatureDef.machine_type_id == obj.machine_type_id,
            StateFeatureDef.feature_key == payload.feature_key,
            StateFeatureDef.id != feature_def_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail=f"Feature key '{payload.feature_key}' already exists")

    state_node_feature_filter = or_(
        StateNode.feature_key == obj.feature_key,
        StateNode.feature_key.like(f"{obj.feature_key}__%"),
    )

    if payload.feature_key != obj.feature_key:
        in_state_nodes = await db.execute(
            select(StateNode.id)
            .where(
                StateNode.machine_type_id == obj.machine_type_id,
                state_node_feature_filter,
            )
            .limit(1)
        )
        if in_state_nodes.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Feature key is used by state nodes and cannot be changed")

    allowed_values = _normalize_allowed_values(payload.allowed_values) or []
    if payload.value_type == "enum" and allowed_values:
        allowed_text = {str(value) for value in allowed_values}
        invalid_state_nodes = await db.execute(
            select(StateNode.target_value)
            .where(
                StateNode.machine_type_id == obj.machine_type_id,
                state_node_feature_filter,
                StateNode.target_value.is_not(None),
            )
            .distinct()
        )
        invalid_values = sorted(
            {
                str(value)
                for value in invalid_state_nodes.scalars().all()
                if str(value) not in allowed_text
            }
        )
        if invalid_values:
            raise HTTPException(
                status_code=409,
                detail=f"Allowed values would invalidate state node targets: {', '.join(invalid_values)}",
            )

    obj.feature_key = payload.feature_key
    obj.feature_name = payload.feature_name
    obj.value_type = payload.value_type
    obj.allowed_values = payload.allowed_values
    concrete_defs = await db.execute(
        select(StateFeatureDef).where(
            StateFeatureDef.machine_type_id == obj.machine_type_id,
            StateFeatureDef.feature_key.like(f"{obj.feature_key}__%"),
        )
    )
    for concrete_def in concrete_defs.scalars().all():
        concrete_def.value_type = payload.value_type
        concrete_def.allowed_values = payload.allowed_values
    await db.flush()
    await db.refresh(obj)
    return _serialize_feature_def(obj)


@router.delete("/feature-defs/{feature_def_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feature_def(feature_def_id: int, db: AsyncSession = Depends(get_db_session)):
    obj = await _get_feature_def_or_404(feature_def_id, db)

    in_states = await db.execute(
        select(MachineStateFeature.id)
        .join(MachineState)
        .join(Machine)
        .where(
            Machine.machine_type_id == obj.machine_type_id,
            MachineStateFeature.feature_key == obj.feature_key,
        )
        .limit(1)
    )
    in_rules = await db.execute(
        select(OpRule.id)
        .where(OpRule.machine_type_id == obj.machine_type_id)
        .join(OpRulePrecond, OpRulePrecond.op_rule_id == OpRule.id, isouter=True)
        .join(OpRuleEffect, OpRuleEffect.op_rule_id == OpRule.id, isouter=True)
        .where(
            or_(
                OpRulePrecond.feature_key == obj.feature_key,
                OpRuleEffect.feature_key == obj.feature_key,
            )
        )
        .limit(1)
    )
    if in_states.scalar_one_or_none() is not None or in_rules.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Feature definition is in use and cannot be deleted")
    in_state_nodes = await db.execute(
        select(StateNode.id)
        .where(
            StateNode.machine_type_id == obj.machine_type_id,
            or_(
                StateNode.feature_key == obj.feature_key,
                StateNode.feature_key.like(f"{obj.feature_key}__%"),
            ),
        )
        .limit(1)
    )
    if in_state_nodes.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Feature definition is used by state nodes and cannot be deleted")

    await db.delete(obj)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================================================
# Layered Activity / State CRUD
# ============================================================


@router.get("/machine-types/{machine_type_id}/atomic-activities", response_model=list[AtomicActivityResponse])
async def list_atomic_activities(machine_type_id: int, db: AsyncSession = Depends(get_db_session)):
    await _get_machine_type_or_404(machine_type_id, db)
    result = await db.execute(
        select(AtomicActivity)
        .where(AtomicActivity.machine_type_id == machine_type_id)
        .order_by(AtomicActivity.sort_order, AtomicActivity.id)
    )
    return [_serialize_atomic_activity(item) for item in result.scalars().all()]


@router.post(
    "/machine-types/{machine_type_id}/atomic-activities",
    response_model=AtomicActivityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_atomic_activity(
    machine_type_id: int,
    payload: AtomicActivityCreate,
    db: AsyncSession = Depends(get_db_session),
):
    machine_type = await _get_machine_type_or_404(machine_type_id, db)
    if payload.machine_type_id != machine_type_id:
        raise HTTPException(status_code=422, detail="Payload machine_type_id must match path machine_type_id")
    code = _clean_optional_code(payload.code)
    if code:
        await _ensure_atomic_code_unique(db, machine_type_id, code)
    else:
        code = await _generate_machine_type_code(db, AtomicActivity, machine_type, "aa")
    payload_data = payload.model_dump()
    payload_data["code"] = code
    obj = AtomicActivity(**payload_data)
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return _serialize_atomic_activity(obj)


@router.put("/atomic-activities/{atomic_activity_id}", response_model=AtomicActivityResponse)
async def update_atomic_activity(
    atomic_activity_id: int,
    payload: AtomicActivityUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_atomic_activity_or_404(atomic_activity_id, db)
    code = _clean_optional_code(payload.code)
    if code:
        await _ensure_atomic_code_unique(db, obj.machine_type_id, code, exclude_id=atomic_activity_id)
        obj.code = code
    obj.name = payload.name
    obj.activity_category = payload.activity_category
    obj.sort_order = payload.sort_order
    obj.is_active = payload.is_active
    obj.metadata_json = payload.metadata_json
    await db.flush()
    await db.refresh(obj)
    return _serialize_atomic_activity(obj)


@router.delete("/atomic-activities/{atomic_activity_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_atomic_activity(atomic_activity_id: int, db: AsyncSession = Depends(get_db_session)):
    obj = await _get_atomic_activity_or_404(atomic_activity_id, db)
    rule_ids = [rule.id for rule in obj.op_rules]
    if rule_ids:
        in_use = await db.execute(
            select(CandidatePlanStep.id)
            .where(CandidatePlanStep.op_rule_id.in_(rule_ids))
            .limit(1)
        )
        if in_use.scalar_one_or_none() is not None:
            raise HTTPException(status_code=409, detail="Atomic activity is used in plans and cannot be deleted")

        await db.execute(delete(OpRulePrecond).where(OpRulePrecond.op_rule_id.in_(rule_ids)))
        await db.execute(delete(OpRuleEffect).where(OpRuleEffect.op_rule_id.in_(rule_ids)))
        await db.execute(delete(OpRuleResourceReq).where(OpRuleResourceReq.op_rule_id.in_(rule_ids)))
        for rule in list(obj.op_rules):
            await db.delete(rule)

    for ref in list(obj.package_refs):
        await db.delete(ref)
    await db.delete(obj)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/activity-nodes/{package_id}/atomic-activity-refs",
    response_model=list[ActivityPackageAtomicRefResponse],
)
async def list_activity_package_atomic_refs(package_id: int, db: AsyncSession = Depends(get_db_session)):
    await _validate_activity_package_for_ref(db, package_id)
    result = await db.execute(
        select(ActivityPackageAtomicRef)
        .where(ActivityPackageAtomicRef.activity_node_id == package_id)
        .options(selectinload(ActivityPackageAtomicRef.atomic_activity))
        .order_by(ActivityPackageAtomicRef.sort_order, ActivityPackageAtomicRef.id)
    )
    return [_serialize_atomic_ref(item) for item in result.scalars().all()]


@router.post(
    "/activity-nodes/{package_id}/atomic-activity-refs",
    response_model=ActivityPackageAtomicRefResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_activity_package_atomic_ref(
    package_id: int,
    payload: ActivityPackageAtomicRefCreate,
    db: AsyncSession = Depends(get_db_session),
):
    package = await _validate_activity_package_for_ref(db, package_id)
    atomic = await _get_atomic_activity_or_404(payload.atomic_activity_id, db)
    if atomic.machine_type_id != package.machine_type_id:
        raise HTTPException(status_code=422, detail="Atomic activity must belong to the same machine type as the activity package")
    existing = await db.execute(
        select(ActivityPackageAtomicRef.id).where(
            ActivityPackageAtomicRef.activity_node_id == package_id,
            ActivityPackageAtomicRef.atomic_activity_id == payload.atomic_activity_id,
        ).limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Atomic activity is already attached to this package")
    obj = ActivityPackageAtomicRef(
        activity_node_id=package_id,
        atomic_activity_id=payload.atomic_activity_id,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
        metadata_json=payload.metadata_json,
    )
    db.add(obj)
    await db.flush()
    obj = await _get_atomic_ref_or_404(obj.id, db)
    return _serialize_atomic_ref(obj)


@router.delete("/activity-package-atomic-refs/{ref_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_activity_package_atomic_ref(ref_id: int, db: AsyncSession = Depends(get_db_session)):
    ref = await _get_atomic_ref_or_404(ref_id, db)
    await db.delete(ref)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/machine-types/{machine_type_id}/activity-nodes", response_model=list[ActivityNodeResponse])
async def list_activity_nodes(machine_type_id: int, db: AsyncSession = Depends(get_db_session)):
    await _get_machine_type_or_404(machine_type_id, db)
    result = await db.execute(
        select(ActivityNode)
        .where(ActivityNode.machine_type_id == machine_type_id)
        .order_by(ActivityNode.level, ActivityNode.sort_order, ActivityNode.id)
    )
    return [_serialize_activity_node(item) for item in result.scalars().all()]


@router.post(
    "/machine-types/{machine_type_id}/activity-nodes",
    response_model=ActivityNodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_activity_node(
    machine_type_id: int,
    payload: ActivityNodeCreate,
    db: AsyncSession = Depends(get_db_session),
):
    machine_type = await _get_machine_type_or_404(machine_type_id, db)
    if payload.machine_type_id != machine_type_id:
        raise HTTPException(status_code=422, detail="Payload machine_type_id must match path machine_type_id")
    code = _clean_optional_code(payload.code)
    if code:
        await _ensure_node_code_unique(db, ActivityNode, machine_type_id, code)
    else:
        code = await _generate_machine_type_code(db, ActivityNode, machine_type, "ap")
    await _validate_activity_parent(db, machine_type_id, payload.level, payload.parent_id)
    payload_data = payload.model_dump()
    payload_data["code"] = code
    obj = ActivityNode(**payload_data)
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return _serialize_activity_node(obj)


@router.put("/activity-nodes/{node_id}", response_model=ActivityNodeResponse)
async def update_activity_node(
    node_id: int,
    payload: ActivityNodeUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_activity_node_or_404(node_id, db)
    if obj.children and payload.level != obj.level:
        raise HTTPException(status_code=422, detail="Cannot change level while activity node has children")
    code = _clean_optional_code(payload.code)
    if code:
        await _ensure_node_code_unique(db, ActivityNode, obj.machine_type_id, code, exclude_id=node_id)
    await _validate_activity_parent(
        db,
        obj.machine_type_id,
        payload.level,
        payload.parent_id,
        current_id=node_id,
    )
    obj.parent_id = payload.parent_id
    obj.level = payload.level
    if code:
        obj.code = code
    obj.name = payload.name
    obj.activity_category = payload.activity_category
    obj.sort_order = payload.sort_order
    obj.is_active = payload.is_active
    obj.metadata_json = payload.metadata_json
    await db.flush()
    await db.refresh(obj)
    return _serialize_activity_node(obj)


@router.delete("/activity-nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_activity_node(node_id: int, db: AsyncSession = Depends(get_db_session)):
    obj = await _get_activity_node_or_404(node_id, db)
    in_maintenance_template = await db.execute(
        select(MaintenanceIntentTemplate.id)
        .where(MaintenanceIntentTemplate.scope_activity_node_id == node_id)
        .limit(1)
    )
    if obj.children or obj.op_rules or obj.scope_guards or in_maintenance_template.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Activity node is in use and cannot be deleted")
    await db.delete(obj)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/machine-types/{machine_type_id}/state-nodes", response_model=list[StateNodeResponse])
async def list_state_nodes(machine_type_id: int, db: AsyncSession = Depends(get_db_session)):
    await _get_machine_type_or_404(machine_type_id, db)
    result = await db.execute(
        select(StateNode)
        .where(StateNode.machine_type_id == machine_type_id)
        .order_by(StateNode.level, StateNode.sort_order, StateNode.id)
    )
    return [_serialize_state_node(item) for item in result.scalars().all()]


@router.post(
    "/machine-types/{machine_type_id}/state-nodes",
    response_model=StateNodeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_state_node(
    machine_type_id: int,
    payload: StateNodeCreate,
    db: AsyncSession = Depends(get_db_session),
):
    machine_type = await _get_machine_type_or_404(machine_type_id, db)
    if payload.machine_type_id != machine_type_id:
        raise HTTPException(status_code=422, detail="Payload machine_type_id must match path machine_type_id")
    code = _clean_optional_code(payload.code)
    if code:
        await _ensure_node_code_unique(db, StateNode, machine_type_id, code)
    else:
        suffix = "sa" if payload.state_kind != "aggregate" else "sp"
        code = await _generate_machine_type_code(db, StateNode, machine_type, suffix)
    await _validate_state_parent(db, machine_type_id, payload.level, payload.parent_id)
    await _validate_state_node_payload(db, machine_type_id, payload)
    payload_data = payload.model_dump()
    payload_data["code"] = code
    obj = StateNode(**payload_data)
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return _serialize_state_node(obj)


@router.put("/state-nodes/{node_id}", response_model=StateNodeResponse)
async def update_state_node(
    node_id: int,
    payload: StateNodeUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_state_node_or_404(node_id, db)
    if obj.children and payload.level != obj.level:
        raise HTTPException(status_code=422, detail="Cannot change level while state node has children")
    code = _clean_optional_code(payload.code)
    if code:
        await _ensure_node_code_unique(db, StateNode, obj.machine_type_id, code, exclude_id=node_id)
    await _validate_state_parent(
        db,
        obj.machine_type_id,
        payload.level,
        payload.parent_id,
        current_id=node_id,
    )
    await _validate_state_node_payload(db, obj.machine_type_id, payload, has_children=bool(obj.children))
    obj.parent_id = payload.parent_id
    obj.level = payload.level
    if code:
        obj.code = code
    obj.name = payload.name
    obj.feature_key = payload.feature_key
    obj.operator = payload.operator
    obj.target_value = payload.target_value
    obj.state_kind = payload.state_kind
    obj.sort_order = payload.sort_order
    obj.is_active = payload.is_active
    obj.metadata_json = payload.metadata_json
    await db.flush()
    await db.refresh(obj)
    return _serialize_state_node(obj)


@router.delete("/state-nodes/{node_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_state_node(node_id: int, db: AsyncSession = Depends(get_db_session)):
    obj = await _get_state_node_or_404(node_id, db)
    if obj.children or obj.scope_guard_preconditions:
        raise HTTPException(status_code=409, detail="State node is in use and cannot be deleted")
    await db.delete(obj)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/activity-nodes/{activity_node_id}/scope-guards", response_model=list[ScopeGuardResponse])
async def list_scope_guards(activity_node_id: int, db: AsyncSession = Depends(get_db_session)):
    await _get_activity_node_or_404(activity_node_id, db)
    result = await db.execute(
        select(ScopeGuard)
        .where(ScopeGuard.activity_node_id == activity_node_id)
        .options(selectinload(ScopeGuard.preconditions).selectinload(ScopeGuardPrecond.state_node))
        .order_by(ScopeGuard.id)
    )
    return [_serialize_scope_guard(item) for item in result.scalars().all()]


@router.post(
    "/activity-nodes/{activity_node_id}/scope-guards",
    response_model=ScopeGuardResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_scope_guard(
    activity_node_id: int,
    payload: ScopeGuardCreate,
    db: AsyncSession = Depends(get_db_session),
):
    activity_node = await _get_activity_node_or_404(activity_node_id, db)
    if payload.activity_node_id != activity_node_id:
        raise HTTPException(status_code=422, detail="Payload activity_node_id must match path activity_node_id")
    await _validate_scope_guard_payload(db, activity_node, payload)
    guard = ScopeGuard(
        activity_node_id=activity_node_id,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
        metadata_json=payload.metadata_json,
    )
    db.add(guard)
    await db.flush()
    await _replace_scope_guard_preconditions(guard, payload, db)
    await db.flush()
    guard = await _get_scope_guard_or_404(guard.id, db)
    return _serialize_scope_guard(guard)


@router.put("/scope-guards/{guard_id}", response_model=ScopeGuardResponse)
async def update_scope_guard(
    guard_id: int,
    payload: ScopeGuardUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    guard = await _get_scope_guard_or_404(guard_id, db)
    await _validate_scope_guard_payload(db, guard.activity_node, payload)
    guard.name = payload.name
    guard.description = payload.description
    guard.is_active = payload.is_active
    guard.metadata_json = payload.metadata_json
    await _replace_scope_guard_preconditions(guard, payload, db)
    await db.flush()
    guard = await _get_scope_guard_or_404(guard.id, db)
    return _serialize_scope_guard(guard)


@router.delete("/scope-guards/{guard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scope_guard(guard_id: int, db: AsyncSession = Depends(get_db_session)):
    guard = await _get_scope_guard_or_404(guard_id, db)
    await db.delete(guard)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/machine-types/{machine_type_id}/layered-expansion",
    response_model=LayeredExpansionResponse,
)
async def preview_layered_expansion(
    machine_type_id: int,
    payload: LayeredExpansionRequest,
    db: AsyncSession = Depends(get_db_session),
):
    await _get_machine_type_or_404(machine_type_id, db)
    return await expand_layered_context(db, machine_type_id, payload)


@router.post(
    "/machine-types/{machine_type_id}/layered-health-check",
    response_model=LayeredHealthCheckResponse,
)
async def preview_layered_health_check(
    machine_type_id: int,
    payload: LayeredExpansionRequest,
    db: AsyncSession = Depends(get_db_session),
):
    await _get_machine_type_or_404(machine_type_id, db)
    return await check_layered_health(db, machine_type_id, payload)


@router.get(
    "/machine-types/{machine_type_id}/maintenance-intent-templates",
    response_model=list[MaintenanceIntentTemplateResponse],
)
async def list_maintenance_intent_templates(
    machine_type_id: int,
    include_inactive: bool = Query(default=True),
    db: AsyncSession = Depends(get_db_session),
):
    await _get_machine_type_or_404(machine_type_id, db)
    query = select(MaintenanceIntentTemplate).where(
        MaintenanceIntentTemplate.machine_type_id == machine_type_id
    )
    if not include_inactive:
        query = query.where(MaintenanceIntentTemplate.is_active.is_(True))
    result = await db.execute(query.order_by(MaintenanceIntentTemplate.issue_type, MaintenanceIntentTemplate.id))
    return [_serialize_maintenance_intent_template(item) for item in result.scalars().all()]


@router.post(
    "/machine-types/{machine_type_id}/maintenance-intent-templates",
    response_model=MaintenanceIntentTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_maintenance_intent_template(
    machine_type_id: int,
    payload: MaintenanceIntentTemplateCreate,
    db: AsyncSession = Depends(get_db_session),
):
    await _get_machine_type_or_404(machine_type_id, db)
    if payload.machine_type_id != machine_type_id:
        raise HTTPException(status_code=422, detail="Payload machine_type_id must match path machine_type_id")
    candidate_scope_ids = await _validate_maintenance_template_payload(db, machine_type_id, payload)
    obj = MaintenanceIntentTemplate(
        machine_type_id=machine_type_id,
        scope_activity_node_id=payload.scope_activity_node_id,
        issue_type=payload.issue_type,
        name=payload.name,
        description=payload.description,
        target_state_node_ids=payload.target_state_node_ids,
        candidate_activity_scope_ids=candidate_scope_ids,
        observed_fact_templates=[
            fact.model_dump(mode="json") for fact in payload.observed_fact_templates
        ],
        desired_fact_templates=[
            fact.model_dump(mode="json") for fact in payload.desired_fact_templates
        ],
        is_active=payload.is_active,
        metadata_json=payload.metadata_json,
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return _serialize_maintenance_intent_template(obj)


@router.put("/maintenance-intent-templates/{template_id}", response_model=MaintenanceIntentTemplateResponse)
async def update_maintenance_intent_template(
    template_id: int,
    payload: MaintenanceIntentTemplateUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_maintenance_intent_template_or_404(template_id, db)
    candidate_scope_ids = await _validate_maintenance_template_payload(
        db,
        obj.machine_type_id,
        payload,
        exclude_id=template_id,
    )
    obj.scope_activity_node_id = payload.scope_activity_node_id
    obj.issue_type = payload.issue_type
    obj.name = payload.name
    obj.description = payload.description
    obj.target_state_node_ids = payload.target_state_node_ids
    obj.candidate_activity_scope_ids = candidate_scope_ids
    obj.observed_fact_templates = [
        fact.model_dump(mode="json") for fact in payload.observed_fact_templates
    ]
    obj.desired_fact_templates = [
        fact.model_dump(mode="json") for fact in payload.desired_fact_templates
    ]
    obj.is_active = payload.is_active
    obj.metadata_json = payload.metadata_json
    await db.flush()
    await db.refresh(obj)
    return _serialize_maintenance_intent_template(obj)


@router.delete("/maintenance-intent-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_maintenance_intent_template(
    template_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_maintenance_intent_template_or_404(template_id, db)
    await db.delete(obj)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/machines", response_model=list[MachineDetailResponse])
async def list_machines(
    machine_type_id: Optional[int] = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
):
    query: Select = select(Machine).options(selectinload(Machine.machine_type)).order_by(Machine.id)
    if machine_type_id is not None:
        query = query.where(Machine.machine_type_id == machine_type_id)

    result = await db.execute(query)
    items = result.scalars().all()
    return [
        {
            "id": item.id,
            "machine_type_id": item.machine_type_id,
            "machine_type_code": item.machine_type.code if item.machine_type else None,
            "code": item.code,
            "name": item.name,
            "location": item.location,
            "created_at": item.created_at,
        }
        for item in items
    ]


@router.post("/machines", response_model=MachineResponse, status_code=status.HTTP_201_CREATED)
async def create_machine(payload: MachineCreate, db: AsyncSession = Depends(get_db_session)):
    await _get_machine_type_or_404(payload.machine_type_id, db)
    await _ensure_unique(db, Machine, "code", payload.code)
    obj = Machine(
        machine_type_id=payload.machine_type_id,
        code=payload.code,
        name=payload.name,
        location=payload.location,
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


@router.put("/machines/{machine_id}", response_model=MachineResponse)
async def update_machine(
    machine_id: int,
    payload: MachineCreate,
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_machine_or_404(machine_id, db)
    await _get_machine_type_or_404(payload.machine_type_id, db)
    await _ensure_unique(db, Machine, "code", payload.code, exclude_id=machine_id)
    obj.machine_type_id = payload.machine_type_id
    obj.code = payload.code
    obj.name = payload.name
    obj.location = payload.location
    await db.flush()
    await db.refresh(obj)
    return obj


@router.delete("/machines/{machine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_machine(machine_id: int, db: AsyncSession = Depends(get_db_session)):
    result = await db.execute(
        select(Machine)
        .where(Machine.id == machine_id)
        .options(selectinload(Machine.machine_states), selectinload(Machine.solve_requests))
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Machine {machine_id} not found")
    if obj.machine_states or obj.solve_requests:
        raise HTTPException(status_code=409, detail="Machine is in use and cannot be deleted")
    await db.delete(obj)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/machines/{machine_id}/states", response_model=MachineStateDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_state(
    machine_id: int,
    payload: MachineStateCreate,
    db: AsyncSession = Depends(get_db_session),
):
    machine = await _get_machine_or_404(machine_id, db)
    await _validate_state_features(db, machine.machine_type_id, payload.features)

    state = MachineState(
        machine_id=machine_id,
        state_type=payload.state_type,
        label=payload.label,
    )
    db.add(state)
    await db.flush()
    await _replace_state_features(state, payload.features, db)
    await db.flush()
    state = await _get_state_or_404(state.id, db)
    return _serialize_state(state)


@router.put("/states/{state_id}", response_model=MachineStateDetailResponse)
async def update_state(
    state_id: int,
    payload: MachineStateUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    state = await _get_state_or_404(state_id, db)
    machine = await _get_machine_or_404(state.machine_id, db)
    await _validate_state_features(db, machine.machine_type_id, payload.features)

    state.state_type = payload.state_type
    state.label = payload.label
    await _replace_state_features(state, payload.features, db)
    await db.flush()
    state = await _get_state_or_404(state.id, db)
    return _serialize_state(state)


@router.delete("/states/{state_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_state(state_id: int, db: AsyncSession = Depends(get_db_session)):
    state = await _get_state_or_404(state_id, db)
    in_use = await db.execute(
        select(SolveRequest.id)
        .where(or_(SolveRequest.current_state_id == state_id, SolveRequest.target_state_id == state_id))
        .limit(1)
    )
    if in_use.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="State is referenced by solve requests and cannot be deleted")

    await db.delete(state)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/machine-types/{machine_type_id}/op-rules", response_model=list[OpRuleDetailResponse])
async def list_op_rules(machine_type_id: int, db: AsyncSession = Depends(get_db_session)):
    await _get_machine_type_or_404(machine_type_id, db)
    result = await db.execute(
        select(OpRule)
        .where(OpRule.machine_type_id == machine_type_id)
        .options(
            selectinload(OpRule.preconditions),
            selectinload(OpRule.effects),
            selectinload(OpRule.resource_reqs),
        )
        .order_by(OpRule.id)
    )
    return [_serialize_rule(item) for item in result.scalars().all()]


@router.post(
    "/machine-types/{machine_type_id}/op-rules",
    response_model=OpRuleDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_op_rule(
    machine_type_id: int,
    payload: OpRuleCreate,
    db: AsyncSession = Depends(get_db_session),
):
    machine_type = await _get_machine_type_or_404(machine_type_id, db)
    if payload.machine_type_id != machine_type_id:
        raise HTTPException(status_code=422, detail="Payload machine_type_id must match path machine_type_id")
    code = _clean_optional_code(payload.code)
    if code:
        await _ensure_unique(db, OpRule, "code", code)
    else:
        code = await _generate_op_rule_code(db, machine_type)
    if not payload.effects:
        raise HTTPException(status_code=422, detail="An operation rule must have at least one effect")
    if payload.activity_node_id and payload.atomic_activity_id:
        raise HTTPException(status_code=422, detail="Use either activity_node_id or atomic_activity_id, not both")
    await _validate_activity_node_for_rule(db, machine_type_id, payload.activity_node_id)
    await _validate_atomic_activity_for_rule(db, machine_type_id, payload.atomic_activity_id)
    await _validate_rule_features(db, machine_type_id, payload.preconditions, payload.effects)

    rule = OpRule(
        machine_type_id=machine_type_id,
        activity_node_id=payload.activity_node_id,
        atomic_activity_id=payload.atomic_activity_id,
        code=code,
        name=payload.name,
        duration_min=payload.duration_min,
        description=payload.description,
        is_active=payload.is_active,
        is_repair=payload.is_repair,
        valid_from=payload.valid_from,
        valid_to=payload.valid_to,
    )
    db.add(rule)
    await db.flush()
    await _replace_rule_children(rule, payload, db)
    await db.flush()
    rule = await _get_rule_or_404(rule.id, db)
    return _serialize_rule(rule)


@router.put("/op-rules/{rule_id}", response_model=OpRuleDetailResponse)
async def update_op_rule(
    rule_id: int,
    payload: OpRuleUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    rule = await _get_rule_or_404(rule_id, db)
    await _get_machine_type_or_404(payload.machine_type_id, db)
    code = _clean_optional_code(payload.code)
    if code:
        await _ensure_unique(db, OpRule, "code", code, exclude_id=rule_id)
    if not payload.effects:
        raise HTTPException(status_code=422, detail="An operation rule must have at least one effect")
    if payload.activity_node_id and payload.atomic_activity_id:
        raise HTTPException(status_code=422, detail="Use either activity_node_id or atomic_activity_id, not both")
    await _validate_activity_node_for_rule(db, payload.machine_type_id, payload.activity_node_id)
    await _validate_atomic_activity_for_rule(db, payload.machine_type_id, payload.atomic_activity_id)
    await _validate_rule_features(db, payload.machine_type_id, payload.preconditions, payload.effects)

    rule.machine_type_id = payload.machine_type_id
    rule.activity_node_id = payload.activity_node_id
    rule.atomic_activity_id = payload.atomic_activity_id
    if code:
        rule.code = code
    rule.name = payload.name
    rule.duration_min = payload.duration_min
    rule.description = payload.description
    rule.is_active = payload.is_active
    rule.is_repair = payload.is_repair
    rule.valid_from = payload.valid_from
    rule.valid_to = payload.valid_to
    await _replace_rule_children(rule, payload, db)
    await db.flush()
    rule = await _get_rule_or_404(rule.id, db)
    return _serialize_rule(rule)


@router.delete("/op-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_op_rule(rule_id: int, db: AsyncSession = Depends(get_db_session)):
    rule = await _get_rule_or_404(rule_id, db)
    in_use = await db.execute(
        select(CandidatePlanStep.id).where(CandidatePlanStep.op_rule_id == rule_id).limit(1)
    )
    if in_use.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="Operation rule is already used in plans and cannot be deleted")
    await db.delete(rule)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/resources", response_model=list[ResourceResponse])
async def list_resources(
    machine_id: int = Query(..., gt=0),
    resource_type: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
):
    await _get_machine_or_404(machine_id, db)
    query: Select = select(Resource).where(Resource.machine_id == machine_id).order_by(Resource.id)
    if resource_type:
        query = query.where(Resource.resource_type == resource_type)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/resources", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(payload: ResourceCreate, db: AsyncSession = Depends(get_db_session)):
    await _get_machine_or_404(payload.machine_id, db)
    await _ensure_resource_code_unique(db, payload.machine_id, payload.code)
    obj = Resource(
        machine_id=payload.machine_id,
        code=payload.code,
        name=payload.name,
        resource_type=payload.resource_type,
        capacity=payload.capacity,
        is_available=payload.is_available,
        meta=payload.meta,
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


@router.put("/resources/{resource_id}", response_model=ResourceResponse)
async def update_resource(
    resource_id: int,
    payload: ResourceUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    obj = await _get_resource_or_404(resource_id, db)
    await _get_machine_or_404(payload.machine_id, db)
    await _ensure_resource_code_unique(db, payload.machine_id, payload.code, exclude_id=resource_id)
    obj.machine_id = payload.machine_id
    obj.code = payload.code
    obj.name = payload.name
    obj.resource_type = payload.resource_type
    obj.capacity = payload.capacity
    obj.is_available = payload.is_available
    obj.meta = payload.meta
    await db.flush()
    await db.refresh(obj)
    return obj


@router.delete("/resources/{resource_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resource(resource_id: int, db: AsyncSession = Depends(get_db_session)):
    obj = await _get_resource_or_404(resource_id, db)
    await db.delete(obj)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ============================================================
# Feature Definition CRUD  GET/POST/PUT/DELETE /features
# ============================================================


async def _get_global_feature_definition_or_404(feature_key: str, db: AsyncSession) -> FeatureDefinition:
    obj = await db.get(FeatureDefinition, feature_key)
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Feature definition '{feature_key}' not found")
    return obj


@router.get("/features", response_model=list[FeatureDefinitionResponse])
async def list_feature_definitions(db: AsyncSession = Depends(get_db_session)):
    """List all global feature definitions (feature_definition table)."""
    result = await db.execute(select(FeatureDefinition).order_by(FeatureDefinition.feature_key))
    return result.scalars().all()


@router.post("/features", response_model=FeatureDefinitionResponse, status_code=status.HTTP_201_CREATED)
async def create_feature_definition(
    payload: FeatureDefinitionCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """Create a global feature definition."""
    existing = await db.get(FeatureDefinition, payload.feature_key)
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Feature key '{payload.feature_key}' already exists")
    obj = FeatureDefinition(
        feature_key=payload.feature_key,
        value_type=payload.value_type,
        allowed_values=payload.allowed_values,
        unit=payload.unit,
        description=payload.description,
    )
    db.add(obj)
    await db.flush()
    await db.refresh(obj)
    return obj


@router.put("/features/{feature_key}", response_model=FeatureDefinitionResponse)
async def update_feature_definition(
    feature_key: str,
    payload: FeatureDefinitionCreate,
    db: AsyncSession = Depends(get_db_session),
):
    """Update a global feature definition."""
    obj = await _get_global_feature_definition_or_404(feature_key, db)
    obj.value_type = payload.value_type
    obj.allowed_values = payload.allowed_values
    obj.unit = payload.unit
    obj.description = payload.description
    await db.flush()
    await db.refresh(obj)
    return obj


@router.delete("/features/{feature_key}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feature_definition(
    feature_key: str,
    db: AsyncSession = Depends(get_db_session),
):
    """Delete a global feature definition."""
    obj = await _get_global_feature_definition_or_404(feature_key, db)
    await db.delete(obj)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
