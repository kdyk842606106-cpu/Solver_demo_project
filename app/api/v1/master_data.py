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
from sqlalchemy import Select, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.services.scheduling_rule_config import (
    SchedulingRuleError,
    scheduling_rule_type_descriptors,
    validate_scheduling_config,
    validate_scheduling_config_references,
)

from app.db.models import (
    ActivityStateBinding,
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
    StateNodeReference,
)
from app.db.schemas import (
    ActivityStateBindingCreate,
    ActivityStateBindingResponse,
    ActivityStateBindingUpdate,
    ActivityPackageAtomicRefCreate,
    ActivityPackageAtomicRefResponse,
    ActivityPackageAtomicRefUpdate,
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
    NetworkEditorCommitRequest,
    NetworkEditorCommitResponse,
    NetworkEditorExportPreviewResponse,
    NetworkEditorGraphResponse,
    NetworkEditorImpactRequest,
    NetworkEditorImpactResponse,
    NetworkEditorRequest,
    NetworkEditorSolverPrecheckResponse,
    NetworkEditorValidationResponse,
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
    StateNodeReferenceCreate,
    StateNodeReferenceResponse,
    StateNodeReferenceUpdate,
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
from app.core.modeling.semantics import (
    is_atomic_state,
    is_legacy_executable_activity,
    is_state_package,
)
from app.services.layered_expansion import expand_layered_context
from app.services.layered_health import check_layered_health
from app.services.network_editor import (
    analyze_network_editor_impact,
    get_network_editor_revision,
    precheck_network_editor_solver,
    project_network_editor_graph,
    validate_network_editor_model,
)

router = APIRouter(tags=["master-data"])


def _domain_error(status_code: int, error_code: str, error_message: str, **details: Any) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={
            "error_code": error_code,
            "error_message": error_message,
            **details,
        },
    )


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
        "is_dimension_template": feature_def.is_dimension_template,
        "dimension_template_id": feature_def.dimension_template_id,
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


async def _get_state_node_reference_or_404(ref_id: int, session: AsyncSession) -> StateNodeReference:
    result = await session.execute(
        select(StateNodeReference)
        .where(StateNodeReference.id == ref_id)
        .options(
            selectinload(StateNodeReference.state_node),
            selectinload(StateNodeReference.parent_state_node),
        )
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"State node reference {ref_id} not found")
    return obj


async def _get_activity_state_binding_or_404(binding_id: int, session: AsyncSession) -> ActivityStateBinding:
    result = await session.execute(
        select(ActivityStateBinding)
        .where(ActivityStateBinding.id == binding_id)
        .options(
            selectinload(ActivityStateBinding.activity_node),
            selectinload(ActivityStateBinding.atomic_activity),
            selectinload(ActivityStateBinding.op_rule),
            selectinload(ActivityStateBinding.state_node),
        )
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise HTTPException(status_code=404, detail=f"Activity-state binding {binding_id} not found")
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
    if level == 3:
        raise _domain_error(
            422,
            "LEGACY_EXECUTABLE_CREATE_FORBIDDEN",
            "ActivityNode(level=3) is read-only legacy data; create an AtomicActivity instead.",
        )
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
    if current_id is not None:
        current_parent_id = parent.parent_id
        seen: set[int] = set()
        while current_parent_id is not None and current_parent_id not in seen:
            if current_parent_id == current_id:
                raise HTTPException(status_code=422, detail="Activity parent would create a cycle")
            seen.add(current_parent_id)
            ancestor = await _get_activity_node_or_404(current_parent_id, session)
            current_parent_id = ancestor.parent_id


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
    if not is_state_package(parent) or parent.feature_key or parent.target_value:
        raise HTTPException(status_code=422, detail="State parent must be an aggregate package before adding children")
    if current_id is not None:
        current_parent_id = parent.parent_id
        seen: set[int] = set()
        while current_parent_id is not None and current_parent_id not in seen:
            if current_parent_id == current_id:
                raise HTTPException(status_code=422, detail="State parent would create a cycle")
            seen.add(current_parent_id)
            ancestor = await _get_state_node_or_404(current_parent_id, session)
            current_parent_id = ancestor.parent_id


def _append_allowed_value(allowed_values: Any, value: str) -> list[Any]:
    values = _normalize_allowed_values(allowed_values) or []
    text_values = {str(item) for item in values}
    if value not in text_values:
        values.append(value)
    return values


def _is_dimension_template_key(feature_key: Optional[str]) -> bool:
    key = str(feature_key or "")
    return "_dim_" in key and "__" not in key


def _dimension_template_key_from_metadata(metadata_json: Optional[dict[str, Any]]) -> Optional[str]:
    if not isinstance(metadata_json, dict):
        return None
    value = metadata_json.get("dimension_template_key")
    text = str(value or "").strip()
    return text or None


def _state_object_name_from_metadata(metadata_json: Optional[dict[str, Any]]) -> Optional[str]:
    if not isinstance(metadata_json, dict):
        return None
    value = metadata_json.get("state_object_name")
    text = str(value or "").strip()
    return text or None


def _normalize_state_object_token(value: str, fallback: str = "object") -> str:
    parts: list[str] = []
    ascii_part: list[str] = []

    def flush_ascii() -> None:
        token = "".join(ascii_part).strip("_")
        if token:
            parts.append(token)
        ascii_part.clear()

    for char in str(value or "").strip().lower():
        if ("a" <= char <= "z") or ("0" <= char <= "9"):
            ascii_part.append(char)
            continue
        if char == "_" or char.isspace() or char.isascii():
            if ascii_part and ascii_part[-1] != "_":
                ascii_part.append("_")
            continue
        flush_ascii()
        parts.append(f"u{ord(char):x}")

    flush_ascii()
    token = re.sub(r"_+", "_", "_".join(parts)).strip("_")
    return token or fallback


def _build_concrete_state_feature_key(template_key: str, state_object_name: str) -> str:
    prefix = f"{template_key}__"
    max_object_length = max(1, 64 - len(prefix))
    object_token = _normalize_state_object_token(state_object_name)[:max_object_length].strip("_") or "object"
    return f"{prefix}{object_token}"


async def _get_state_dimension_template_def(
    session: AsyncSession,
    machine_type_id: int,
    template_key: str,
) -> StateFeatureDef:
    result = await session.execute(
        select(StateFeatureDef).where(
            StateFeatureDef.machine_type_id == machine_type_id,
            StateFeatureDef.feature_key == template_key,
        )
    )
    template_def = result.scalar_one_or_none()
    if template_def is None:
        raise HTTPException(status_code=422, detail="State dimension template does not exist for this machine type")
    if not _is_dimension_template_key(template_def.feature_key):
        raise HTTPException(status_code=422, detail="State dimension template key must contain '_dim_' and must not contain '__'")
    if template_def.value_type != "enum":
        raise HTTPException(status_code=422, detail="State dimension template must be an enum")
    allowed_values = _normalize_allowed_values(template_def.allowed_values)
    if len({str(value) for value in (allowed_values or [])}) != 2:
        raise HTTPException(status_code=422, detail="State dimension template must define exactly two allowed values")
    return template_def


async def _ensure_state_feature_def_from_template(
    session: AsyncSession,
    machine_type_id: int,
    *,
    feature_key: str,
    feature_name: str,
    template_def: StateFeatureDef,
) -> None:
    allowed_values = _normalize_allowed_values(template_def.allowed_values) or []
    template_name = template_def.feature_name or template_def.feature_key
    concrete_name = f"{feature_name} / {template_name}"

    global_def = await session.get(FeatureDefinition, feature_key)
    if global_def is None:
        session.add(
            FeatureDefinition(
                feature_key=feature_key,
                value_type=template_def.value_type,
                allowed_values=allowed_values,
                description=f"Auto-created from state dimension template '{template_def.feature_key}'",
            )
        )
    elif global_def.value_type == "enum":
        global_def.allowed_values = allowed_values

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
                feature_name=concrete_name,
                value_type=template_def.value_type,
                allowed_values=allowed_values,
                dimension_template_id=template_def.id,
            )
        )
    else:
        feature_def.feature_name = concrete_name
        feature_def.value_type = template_def.value_type
        feature_def.allowed_values = allowed_values
        feature_def.dimension_template_id = template_def.id


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
    current_id: Optional[int] = None,
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

    template_key = _dimension_template_key_from_metadata(payload.metadata_json)
    if template_key:
        template_def = await _get_state_dimension_template_def(session, machine_type_id, template_key)
        state_object_name = _state_object_name_from_metadata(payload.metadata_json)
        if not state_object_name:
            raise HTTPException(status_code=422, detail="Atomic state object name is required for template-backed states")
        expected_feature_key = _build_concrete_state_feature_key(template_key, state_object_name)
        if str(payload.feature_key) != expected_feature_key:
            raise HTTPException(status_code=422, detail="Atomic state feature_key must be derived from its dimension template and state object")
        allowed_values = _normalize_allowed_values(template_def.allowed_values) or []
        if str(payload.target_value) not in {str(value) for value in allowed_values}:
            raise HTTPException(status_code=422, detail="Atomic state target_value must be one of the template allowed values")
        duplicate_conditions = [
            StateNode.machine_type_id == machine_type_id,
            StateNode.state_kind != "aggregate",
            StateNode.feature_key == payload.feature_key,
            StateNode.target_value == payload.target_value,
        ]
        if current_id is not None:
            duplicate_conditions.append(StateNode.id != current_id)
        duplicate_result = await session.execute(
            select(StateNode.id, StateNode.name).where(*duplicate_conditions)
        )
        duplicate = duplicate_result.first()
        if duplicate is not None:
            raise HTTPException(
                status_code=409,
                detail=f"Atomic state fact is already defined by state '{duplicate.name}'",
            )
        await _ensure_state_feature_def_from_template(
            session,
            machine_type_id,
            feature_key=payload.feature_key,
            feature_name=payload.name,
            template_def=template_def,
        )
        return

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


async def _load_state_nodes_for_machine(session: AsyncSession, machine_type_id: int) -> list[StateNode]:
    result = await session.execute(
        select(StateNode)
        .where(StateNode.machine_type_id == machine_type_id)
        .order_by(StateNode.level, StateNode.sort_order, StateNode.id)
    )
    return list(result.scalars().all())


async def _load_state_references_for_machine(session: AsyncSession, machine_type_id: int) -> list[StateNodeReference]:
    result = await session.execute(
        select(StateNodeReference)
        .join(StateNode, StateNodeReference.state_node_id == StateNode.id)
        .where(StateNode.machine_type_id == machine_type_id)
        .order_by(StateNodeReference.parent_state_node_id, StateNodeReference.sort_order, StateNodeReference.id)
    )
    return list(result.scalars().all())


def _state_children_by_parent(
    nodes: list[StateNode],
    references: Optional[list[StateNodeReference]] = None,
    *,
    active_only: bool,
) -> dict[Optional[int], list[StateNode]]:
    by_parent: dict[Optional[int], list[StateNode]] = {}
    by_id = {node.id: node for node in nodes}
    seen: set[tuple[Optional[int], int]] = set()
    for node in nodes:
        parent = by_id.get(node.parent_id) if node.parent_id is not None else None
        if active_only and (not node.is_active or (parent is not None and not parent.is_active)):
            continue
        key = (node.parent_id, node.id)
        by_parent.setdefault(node.parent_id, []).append(node)
        seen.add(key)

    for ref in references or []:
        if not ref.is_active:
            continue
        node = by_id.get(ref.state_node_id)
        parent = by_id.get(ref.parent_state_node_id)
        if node is None or parent is None:
            continue
        if active_only and (not node.is_active or not parent.is_active):
            continue
        key = (ref.parent_state_node_id, ref.state_node_id)
        if key in seen:
            continue
        by_parent.setdefault(ref.parent_state_node_id, []).append(node)
        seen.add(key)

    for children in by_parent.values():
        children.sort(key=lambda item: (item.sort_order, item.id))
    return by_parent


def _leaf_ids_under_state(
    state_node_id: int,
    nodes: list[StateNode],
    references: Optional[list[StateNodeReference]] = None,
    *,
    active_only: bool,
) -> list[int]:
    by_id = {node.id: node for node in nodes}
    by_parent = _state_children_by_parent(nodes, references, active_only=active_only)

    def walk(node_id: int) -> list[int]:
        node = by_id.get(node_id)
        if node is None:
            return []
        if active_only and not node.is_active:
            return []
        children = by_parent.get(node_id, [])
        if is_atomic_state(node):
            return [node_id]
        leaf_ids: list[int] = []
        for child in children:
            leaf_ids.extend(walk(child.id))
        return leaf_ids

    return walk(state_node_id)


def _binding_type_for_state(
    state_node: StateNode,
    nodes: list[StateNode],
    references: Optional[list[StateNodeReference]] = None,
) -> str:
    children = _state_children_by_parent(nodes, references, active_only=True)
    has_children = bool(children.get(state_node.id))
    if not has_children and is_atomic_state(state_node):
        return "atomic_state"
    return "state_package"


def _compute_coverage_status(
    binding: ActivityStateBinding,
    nodes: list[StateNode],
    references: Optional[list[StateNodeReference]] = None,
) -> str:
    active_leaf_ids = set(_leaf_ids_under_state(binding.state_node_id, nodes, references, active_only=True))
    all_leaf_ids = set(_leaf_ids_under_state(binding.state_node_id, nodes, references, active_only=False))
    covered_ids = {int(item) for item in (binding.covered_leaf_state_ids or [])}

    if not covered_ids:
        return "stale"
    if not covered_ids.issubset(all_leaf_ids):
        return "stale"
    if covered_ids == active_leaf_ids and active_leaf_ids:
        return "complete"
    if covered_ids.issubset(active_leaf_ids):
        return "partial" if binding.coverage_status == "partial" else "stale"
    return "stale"


async def _resolve_covered_leaf_ids(
    session: AsyncSession,
    state_node: StateNode,
    explicit_ids: Optional[list[int]],
) -> list[int]:
    nodes = await _load_state_nodes_for_machine(session, state_node.machine_type_id)
    references = await _load_state_references_for_machine(session, state_node.machine_type_id)
    all_leaf_ids = set(_leaf_ids_under_state(state_node.id, nodes, references, active_only=False))
    active_leaf_ids = _leaf_ids_under_state(state_node.id, nodes, references, active_only=True)
    if explicit_ids is None:
        return active_leaf_ids

    explicit_set = {int(item) for item in explicit_ids}
    if len(explicit_set) != len(explicit_ids):
        raise HTTPException(status_code=422, detail="covered_leaf_state_ids cannot contain duplicates")
    if not explicit_set.issubset(all_leaf_ids):
        raise HTTPException(status_code=422, detail="covered_leaf_state_ids must belong to the bound state package")
    return sorted(explicit_set)


async def _validate_state_reference(
    session: AsyncSession,
    state_node: StateNode,
    parent_state_node: StateNode,
) -> None:
    if state_node.id == parent_state_node.id:
        raise HTTPException(status_code=422, detail="State reference cannot point to itself")
    if state_node.machine_type_id != parent_state_node.machine_type_id:
        raise _domain_error(
            422,
            "REFERENCE_CROSS_MACHINE_TYPE",
            "State package and state body must belong to the same machine type.",
        )
    if not is_atomic_state(state_node):
        raise HTTPException(
            status_code=422,
            detail="StateNodeReference membership can only target an atomic state body",
        )
    if not is_state_package(parent_state_node):
        raise HTTPException(
            status_code=422,
            detail="StateNodeReference parent must be an aggregate state package",
        )
    existing = await session.execute(
        select(StateNodeReference.id)
        .where(
            StateNodeReference.state_node_id == state_node.id,
            StateNodeReference.parent_state_node_id == parent_state_node.id,
        )
        .limit(1)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="State node reference already exists")

    nodes = await _load_state_nodes_for_machine(session, state_node.machine_type_id)
    refs = await session.execute(
        select(StateNodeReference).where(
            StateNodeReference.state_node.has(machine_type_id=state_node.machine_type_id)
        )
    )
    adjacency: dict[int, list[int]] = {}
    for node in nodes:
        if node.parent_id is not None:
            adjacency.setdefault(node.parent_id, []).append(node.id)
    for ref in refs.scalars().all():
        adjacency.setdefault(ref.parent_state_node_id, []).append(ref.state_node_id)
    adjacency.setdefault(parent_state_node.id, []).append(state_node.id)

    stack = [state_node.id]
    seen: set[int] = set()
    while stack:
        current = stack.pop()
        if current == parent_state_node.id:
            raise HTTPException(status_code=422, detail="State reference would create a cycle")
        if current in seen:
            continue
        seen.add(current)
        stack.extend(adjacency.get(current, []))


async def _resolve_binding_payload(
    session: AsyncSession,
    payload: ActivityStateBindingCreate | ActivityStateBindingUpdate,
) -> tuple[Optional[ActivityNode], Optional[AtomicActivity], Optional[OpRule], StateNode, str, list[int], str]:
    valid_roles = {"input", "output", "context_input", "declared_output"}
    if payload.binding_role not in valid_roles:
        raise HTTPException(status_code=422, detail="Invalid binding_role")
    if bool(payload.activity_node_id) == bool(payload.atomic_activity_id):
        raise HTTPException(status_code=422, detail="Use either activity_node_id or atomic_activity_id, not both")

    await _get_machine_type_or_404(payload.machine_type_id, session)
    state_node = await _get_state_node_or_404(payload.state_node_id, session)
    if state_node.machine_type_id != payload.machine_type_id:
        raise HTTPException(status_code=422, detail="State node must belong to the same machine type as the binding")

    activity_node: Optional[ActivityNode] = None
    atomic_activity: Optional[AtomicActivity] = None
    op_rule: Optional[OpRule] = None
    if payload.activity_node_id:
        activity_node = await _get_activity_node_or_404(payload.activity_node_id, session)
        if activity_node.machine_type_id != payload.machine_type_id:
            raise HTTPException(status_code=422, detail="Activity node must belong to the same machine type as the binding")
        raise _domain_error(
            410,
            "ACTIVITY_PACKAGE_BINDING_SUNSET",
            "Historical activity-package bindings are audit-only; bind the state to an atomic activity.",
        )
    else:
        atomic_activity = await _get_atomic_activity_or_404(payload.atomic_activity_id or 0, session)
        if atomic_activity.machine_type_id != payload.machine_type_id:
            raise HTTPException(status_code=422, detail="Atomic activity must belong to the same machine type as the binding")
        if payload.binding_role not in {"input", "output"}:
            raise HTTPException(status_code=422, detail="Executable bindings only support input or output roles")
        if payload.op_rule_id is None:
            active_rules = [
                rule for rule in atomic_activity.op_rules
                if rule.atomic_activity_id == atomic_activity.id and rule.is_active
            ]
            if len(active_rules) == 1:
                op_rule = active_rules[0]
            elif len(active_rules) > 1:
                raise HTTPException(status_code=422, detail="Executable binding requires explicit op_rule_id when atomic activity has multiple active rules")
        else:
            op_rule = await _get_rule_or_404(payload.op_rule_id, session)
            if op_rule.machine_type_id != payload.machine_type_id:
                raise HTTPException(status_code=422, detail="Op rule must belong to the same machine type as the binding")
            if op_rule.atomic_activity_id != atomic_activity.id:
                raise HTTPException(status_code=422, detail="Op rule must bind to the same atomic activity")

    covered_leaf_ids = await _resolve_covered_leaf_ids(session, state_node, payload.covered_leaf_state_ids)
    nodes = await _load_state_nodes_for_machine(session, state_node.machine_type_id)
    references = await _load_state_references_for_machine(session, state_node.machine_type_id)
    binding_type = _binding_type_for_state(state_node, nodes, references)
    temp_binding = ActivityStateBinding(
        machine_type_id=payload.machine_type_id,
        state_node_id=state_node.id,
        binding_role=payload.binding_role,
        binding_type=binding_type,
        covered_leaf_state_ids=covered_leaf_ids,
        coverage_status="partial" if payload.covered_leaf_state_ids is not None else "complete",
    )
    coverage_status = _compute_coverage_status(temp_binding, nodes, references)
    return activity_node, atomic_activity, op_rule, state_node, binding_type, covered_leaf_ids, coverage_status


def _is_executable_rule_binding_role(binding_role: Optional[str]) -> bool:
    return binding_role in {"input", "output"}


_BINDING_MANAGED_FACTS_METADATA_KEY = "_network_editor_managed_rule_facts"


def _fact_key_to_metadata(binding_role: str, key: tuple[str, str, str]) -> dict[str, str]:
    feature_key, operator_or_effect_type, value = key
    if binding_role == "input":
        return {
            "feature_key": feature_key,
            "operator": operator_or_effect_type,
            "feature_value": value,
        }
    return {
        "feature_key": feature_key,
        "effect_type": operator_or_effect_type,
        "new_value": value,
    }


def _fact_key_from_metadata(binding_role: str, item: Any) -> tuple[str, str, str] | None:
    if not isinstance(item, dict):
        return None
    feature_key = item.get("feature_key")
    if not feature_key:
        return None
    if binding_role == "input":
        operator = item.get("operator") or "eq"
        feature_value = item.get("feature_value")
        if feature_value is None:
            return None
        return (str(feature_key), str(operator), str(feature_value))
    effect_type = item.get("effect_type") or "set"
    new_value = item.get("new_value")
    if new_value is None:
        return None
    return (str(feature_key), str(effect_type), str(new_value))


def _binding_managed_rule_fact_keys(
    binding: ActivityStateBinding,
    binding_role: Optional[str] = None,
) -> set[tuple[str, str, str]]:
    role = binding_role or binding.binding_role
    if not _is_executable_rule_binding_role(role):
        return set()
    metadata = binding.metadata_json if isinstance(binding.metadata_json, dict) else {}
    fact_metadata = metadata.get(_BINDING_MANAGED_FACTS_METADATA_KEY)
    if not isinstance(fact_metadata, dict):
        return set()
    raw_items = fact_metadata.get(role)
    if not isinstance(raw_items, list):
        return set()
    keys: set[tuple[str, str, str]] = set()
    for item in raw_items:
        key = _fact_key_from_metadata(role, item)
        if key is not None:
            keys.add(key)
    return keys


def _set_binding_managed_rule_fact_keys(
    binding: ActivityStateBinding,
    binding_role: str,
    keys: set[tuple[str, str, str]],
) -> None:
    metadata = dict(binding.metadata_json or {})
    fact_metadata = metadata.get(_BINDING_MANAGED_FACTS_METADATA_KEY)
    if not isinstance(fact_metadata, dict):
        fact_metadata = {}
    else:
        fact_metadata = dict(fact_metadata)

    if keys:
        fact_metadata[binding_role] = [
            _fact_key_to_metadata(binding_role, key)
            for key in sorted(keys, key=lambda item: (item[0], item[1], item[2]))
        ]
    else:
        fact_metadata.pop(binding_role, None)

    if fact_metadata:
        metadata[_BINDING_MANAGED_FACTS_METADATA_KEY] = fact_metadata
    else:
        metadata.pop(_BINDING_MANAGED_FACTS_METADATA_KEY, None)
    binding.metadata_json = metadata or None


async def _rule_fact_keys_for_leaf_ids(
    session: AsyncSession,
    binding_role: Optional[str],
    leaf_ids: list[int] | None,
) -> set[tuple[str, str, str]]:
    if not _is_executable_rule_binding_role(binding_role) or not leaf_ids:
        return set()
    result = await session.execute(select(StateNode).where(StateNode.id.in_(leaf_ids)))
    keys: set[tuple[str, str, str]] = set()
    for leaf in result.scalars().all():
        if not leaf.feature_key or leaf.target_value is None:
            continue
        if binding_role == "input":
            keys.add((leaf.feature_key, leaf.operator or "eq", leaf.target_value))
        else:
            keys.add((leaf.feature_key, "set", leaf.target_value))
    return keys


async def _rule_fact_keys_for_binding(
    session: AsyncSession,
    binding: ActivityStateBinding,
) -> set[tuple[str, str, str]]:
    if binding.atomic_activity_id is None or binding.op_rule_id is None:
        return set()
    return await _rule_fact_keys_for_leaf_ids(session, binding.binding_role, binding.covered_leaf_state_ids or [])


async def _managed_rule_fact_keys_for_active_bindings(
    session: AsyncSession,
    op_rule_id: int,
    binding_role: str,
    *,
    exclude_binding_id: Optional[int] = None,
) -> set[tuple[str, str, str]]:
    result = await session.execute(
        select(ActivityStateBinding).where(
            ActivityStateBinding.op_rule_id == op_rule_id,
            ActivityStateBinding.binding_role == binding_role,
            ActivityStateBinding.atomic_activity_id.is_not(None),
            ActivityStateBinding.is_active.is_(True),
        )
    )
    keys: set[tuple[str, str, str]] = set()
    for binding in result.scalars().all():
        if exclude_binding_id is not None and binding.id == exclude_binding_id:
            continue
        keys.update(_binding_managed_rule_fact_keys(binding, binding_role))
    return keys


async def _existing_rule_fact_keys(
    session: AsyncSession,
    op_rule_id: int,
    binding_role: str,
    keys: set[tuple[str, str, str]],
) -> set[tuple[str, str, str]]:
    existing_keys: set[tuple[str, str, str]] = set()
    for feature_key, operator_or_effect_type, value in keys:
        if binding_role == "input":
            exists = await session.execute(
                select(OpRulePrecond.id)
                .where(
                    OpRulePrecond.op_rule_id == op_rule_id,
                    OpRulePrecond.feature_key == feature_key,
                    OpRulePrecond.operator == operator_or_effect_type,
                    OpRulePrecond.feature_value == value,
                )
                .limit(1)
            )
        else:
            exists = await session.execute(
                select(OpRuleEffect.id)
                .where(
                    OpRuleEffect.op_rule_id == op_rule_id,
                    OpRuleEffect.feature_key == feature_key,
                    OpRuleEffect.effect_type == operator_or_effect_type,
                    OpRuleEffect.new_value == value,
                )
                .limit(1)
            )
        if exists.scalar_one_or_none() is not None:
            existing_keys.add((feature_key, operator_or_effect_type, value))
    return existing_keys


async def _sync_binding_rule_facts(
    binding: ActivityStateBinding,
    session: AsyncSession,
    *,
    previous_managed_keys: set[tuple[str, str, str]] | None = None,
) -> None:
    if binding.op_rule_id is None or not _is_executable_rule_binding_role(binding.binding_role):
        metadata = dict(binding.metadata_json or {})
        metadata.pop(_BINDING_MANAGED_FACTS_METADATA_KEY, None)
        binding.metadata_json = metadata or None
        return

    desired_keys = set()
    if binding.atomic_activity_id is not None and binding.is_active:
        desired_keys = await _rule_fact_keys_for_binding(session, binding)

    existing_keys = await _existing_rule_fact_keys(
        session,
        binding.op_rule_id,
        binding.binding_role,
        desired_keys,
    )
    keys_to_add = desired_keys - existing_keys
    if keys_to_add:
        await _add_rule_facts_for_keys(session, binding.op_rule_id, binding.binding_role, keys_to_add)

    managed_by_other = await _managed_rule_fact_keys_for_active_bindings(
        session,
        binding.op_rule_id,
        binding.binding_role,
        exclude_binding_id=binding.id,
    )
    previous_managed_keys = previous_managed_keys or set()
    managed_keys = (
        keys_to_add
        | (desired_keys & managed_by_other)
        | (desired_keys & previous_managed_keys)
    )
    _set_binding_managed_rule_fact_keys(binding, binding.binding_role, managed_keys)


async def _desired_rule_fact_keys(
    session: AsyncSession,
    op_rule_id: Optional[int],
    binding_role: Optional[str],
) -> set[tuple[str, str, str]]:
    if op_rule_id is None or not _is_executable_rule_binding_role(binding_role):
        return set()
    result = await session.execute(
        select(ActivityStateBinding).where(
            ActivityStateBinding.op_rule_id == op_rule_id,
            ActivityStateBinding.binding_role == binding_role,
            ActivityStateBinding.atomic_activity_id.is_not(None),
            ActivityStateBinding.is_active.is_(True),
        )
    )
    leaf_ids: set[int] = set()
    for binding in result.scalars().all():
        leaf_ids.update(int(item) for item in (binding.covered_leaf_state_ids or []))
    return await _rule_fact_keys_for_leaf_ids(session, binding_role, sorted(leaf_ids))


async def _add_rule_facts_for_keys(
    session: AsyncSession,
    op_rule_id: int,
    binding_role: str,
    keys: set[tuple[str, str, str]],
) -> None:
    if binding_role == "input":
        for feature_key, operator, feature_value in keys:
            exists = await session.execute(
                select(OpRulePrecond.id)
                .where(
                    OpRulePrecond.op_rule_id == op_rule_id,
                    OpRulePrecond.feature_key == feature_key,
                    OpRulePrecond.operator == operator,
                    OpRulePrecond.feature_value == feature_value,
                )
                .limit(1)
            )
            if exists.scalar_one_or_none() is None:
                session.add(
                    OpRulePrecond(
                        op_rule_id=op_rule_id,
                        feature_key=feature_key,
                        operator=operator,
                        feature_value=feature_value,
                        value_list=None,
                    )
                )
    else:
        for feature_key, effect_type, new_value in keys:
            exists = await session.execute(
                select(OpRuleEffect.id)
                .where(
                    OpRuleEffect.op_rule_id == op_rule_id,
                    OpRuleEffect.feature_key == feature_key,
                    OpRuleEffect.new_value == new_value,
                    OpRuleEffect.effect_type == effect_type,
                )
                .limit(1)
            )
            if exists.scalar_one_or_none() is None:
                session.add(
                    OpRuleEffect(
                        op_rule_id=op_rule_id,
                        feature_key=feature_key,
                        new_value=new_value,
                        effect_type=effect_type,
                        delta_value=None,
                    )
                )


async def _remove_rule_facts_for_keys(
    session: AsyncSession,
    op_rule_id: int,
    binding_role: str,
    keys: set[tuple[str, str, str]],
) -> None:
    for feature_key, operator_or_effect_type, value in keys:
        if binding_role == "input":
            await session.execute(
                delete(OpRulePrecond).where(
                    OpRulePrecond.op_rule_id == op_rule_id,
                    OpRulePrecond.feature_key == feature_key,
                    OpRulePrecond.operator == operator_or_effect_type,
                    OpRulePrecond.feature_value == value,
                )
            )
        else:
            await session.execute(
                delete(OpRuleEffect).where(
                    OpRuleEffect.op_rule_id == op_rule_id,
                    OpRuleEffect.feature_key == feature_key,
                    OpRuleEffect.effect_type == operator_or_effect_type,
                    OpRuleEffect.new_value == value,
                )
            )


async def _reconcile_rule_binding_facts(
    session: AsyncSession,
    op_rule_id: Optional[int],
    binding_role: Optional[str],
    *,
    stale_keys: set[tuple[str, str, str]] | None = None,
) -> None:
    if op_rule_id is None or not _is_executable_rule_binding_role(binding_role):
        return
    desired_keys = await _desired_rule_fact_keys(session, op_rule_id, binding_role)
    stale_without_active_binding = (stale_keys or set()) - desired_keys
    if stale_without_active_binding:
        await _remove_rule_facts_for_keys(session, op_rule_id, binding_role, stale_without_active_binding)


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
        "description": node.description,
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
        "description": activity.description,
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


def _serialize_state_node_reference(ref: StateNodeReference) -> dict[str, Any]:
    state_node = ref.state_node
    parent_state_node = ref.parent_state_node
    return {
        "id": ref.id,
        "state_node_id": ref.state_node_id,
        "state_node_code": state_node.code if state_node else None,
        "state_node_name": state_node.name if state_node else None,
        "parent_state_node_id": ref.parent_state_node_id,
        "parent_state_node_code": parent_state_node.code if parent_state_node else None,
        "parent_state_node_name": parent_state_node.name if parent_state_node else None,
        "sort_order": ref.sort_order,
        "is_active": ref.is_active,
        "metadata_json": ref.metadata_json,
        "created_at": ref.created_at,
    }


async def _serialize_activity_state_binding(
    binding: ActivityStateBinding,
    session: AsyncSession,
) -> dict[str, Any]:
    nodes = await _load_state_nodes_for_machine(session, binding.machine_type_id)
    references = await _load_state_references_for_machine(session, binding.machine_type_id)
    coverage_status = _compute_coverage_status(binding, nodes, references)
    if binding.coverage_status != coverage_status:
        binding.coverage_status = coverage_status

    activity_node = binding.activity_node
    atomic_activity = binding.atomic_activity
    op_rule = binding.op_rule
    state_node = binding.state_node
    return {
        "id": binding.id,
        "machine_type_id": binding.machine_type_id,
        "activity_node_id": binding.activity_node_id,
        "activity_node_code": activity_node.code if activity_node else None,
        "activity_node_name": activity_node.name if activity_node else None,
        "atomic_activity_id": binding.atomic_activity_id,
        "atomic_activity_code": atomic_activity.code if atomic_activity else None,
        "atomic_activity_name": atomic_activity.name if atomic_activity else None,
        "op_rule_id": binding.op_rule_id,
        "op_rule_code": op_rule.code if op_rule else None,
        "op_rule_name": op_rule.name if op_rule else None,
        "state_node_id": binding.state_node_id,
        "state_node_code": state_node.code if state_node else None,
        "state_node_name": state_node.name if state_node else None,
        "binding_role": binding.binding_role,
        "binding_type": binding.binding_type,
        "coverage_policy": binding.coverage_policy,
        "covered_leaf_state_ids": binding.covered_leaf_state_ids or [],
        "coverage_status": binding.coverage_status,
        "is_inherited": binding.is_inherited,
        "is_active": binding.is_active,
        "metadata_json": binding.metadata_json,
        "created_at": binding.created_at,
        "updated_at": binding.updated_at,
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
            "scheduling_config": item.scheduling_config,
            "created_at": item.created_at,
            "feature_defs": [_serialize_feature_def(feature_def) for feature_def in item.state_feature_defs],
        }
        for item in items
    ]


@router.get("/scheduling-rule-types")
async def list_scheduling_rule_types():
    return scheduling_rule_type_descriptors()


@router.post("/machine-types", response_model=MachineTypeResponse, status_code=status.HTTP_201_CREATED)
async def create_machine_type(
    payload: MachineTypeCreate,
    db: AsyncSession = Depends(get_db_session),
):
    await _ensure_unique(db, MachineType, "code", payload.code)
    try:
        scheduling_config = validate_scheduling_config(payload.scheduling_config)
    except SchedulingRuleError as exc:
        raise HTTPException(status_code=422, detail={"error_code": exc.code, "error_message": str(exc)}) from exc
    obj = MachineType(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        scheduling_config=scheduling_config,
    )
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
    try:
        scheduling_config = validate_scheduling_config(payload.scheduling_config)
        await validate_scheduling_config_references(machine_type_id, scheduling_config, db)
    except SchedulingRuleError as exc:
        raise HTTPException(status_code=422, detail={"error_code": exc.code, "error_message": str(exc)}) from exc
    configured_subsystems = {
        item["code"] for item in (scheduling_config or {}).get("responsible_subsystems", [])
    }
    atomic_result = await db.execute(
        select(AtomicActivity).where(AtomicActivity.machine_type_id == machine_type_id)
    )
    used_subsystems = {
        str(item.metadata_json.get("responsible_subsystem"))
        for item in atomic_result.scalars().all()
        if isinstance(item.metadata_json, dict) and item.metadata_json.get("responsible_subsystem")
    }
    missing = used_subsystems - configured_subsystems
    if missing:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": "RESPONSIBLE_SUBSYSTEM_IN_USE",
                "error_message": f"Responsible subsystems are still used: {sorted(missing)}",
            },
        )
    obj.code = payload.code
    obj.name = payload.name
    obj.description = payload.description
    obj.scheduling_config = scheduling_config
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
        is_dimension_template=payload.is_dimension_template,
        dimension_template_id=payload.dimension_template_id,
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
    obj.is_dimension_template = payload.is_dimension_template
    obj.dimension_template_id = payload.dimension_template_id
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


def _validate_atomic_responsible_subsystem(
    machine_type: MachineType,
    metadata_json: Optional[dict[str, Any]],
) -> None:
    if not isinstance(metadata_json, dict) or not metadata_json.get("responsible_subsystem"):
        return
    value = str(metadata_json["responsible_subsystem"]).strip()
    configured = {
        str(item.get("code"))
        for item in (machine_type.scheduling_config or {}).get("responsible_subsystems", [])
        if item.get("code")
    }
    if value not in configured:
        raise HTTPException(
            status_code=422,
            detail={
                "error_code": "RESPONSIBLE_SUBSYSTEM_INVALID",
                "error_message": f"Unknown responsible subsystem: {value}",
            },
        )


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
    _validate_atomic_responsible_subsystem(machine_type, payload.metadata_json)
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
    machine_type = await _get_machine_type_or_404(obj.machine_type_id, db)
    _validate_atomic_responsible_subsystem(machine_type, payload.metadata_json)
    code = _clean_optional_code(payload.code)
    if code:
        await _ensure_atomic_code_unique(db, obj.machine_type_id, code, exclude_id=atomic_activity_id)
        obj.code = code
    obj.name = payload.name
    obj.description = payload.description
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
    reference_count = int(
        (await db.execute(
            select(func.count(ActivityPackageAtomicRef.id)).where(
                ActivityPackageAtomicRef.atomic_activity_id == atomic_activity_id
            )
        )).scalar_one()
    )
    rule_count = int(
        (await db.execute(
            select(func.count(OpRule.id)).where(OpRule.atomic_activity_id == atomic_activity_id)
        )).scalar_one()
    )
    binding_count = int(
        (await db.execute(
            select(func.count(ActivityStateBinding.id)).where(
                ActivityStateBinding.atomic_activity_id == atomic_activity_id
            )
        )).scalar_one()
    )
    plan_step_count = int(
        (await db.execute(
            select(func.count(CandidatePlanStep.id))
            .join(OpRule, CandidatePlanStep.op_rule_id == OpRule.id)
            .where(OpRule.atomic_activity_id == atomic_activity_id)
        )).scalar_one()
    )
    dependencies = {
        "package_references": reference_count,
        "rules": rule_count,
        "state_bindings": binding_count,
        "plan_steps": plan_step_count,
    }
    if any(dependencies.values()):
        raise _domain_error(
            409,
            "BODY_IN_USE",
            "Atomic activity is still referenced; remove its relationships before deleting the body.",
            dependencies=dependencies,
        )
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
        raise _domain_error(
            422,
            "REFERENCE_CROSS_MACHINE_TYPE",
            "Activity package and atomic activity body must belong to the same machine type.",
        )
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


@router.put(
    "/activity-package-atomic-refs/{ref_id}",
    response_model=ActivityPackageAtomicRefResponse,
)
async def update_activity_package_atomic_ref(
    ref_id: int,
    payload: ActivityPackageAtomicRefUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    ref = await _get_atomic_ref_or_404(ref_id, db)
    await _validate_activity_package_for_ref(db, ref.activity_node_id)
    if (
        payload.atomic_activity_id is not None
        and payload.atomic_activity_id != ref.atomic_activity_id
    ):
        raise _domain_error(
            409,
            "RELATION_ENDPOINT_IMMUTABLE",
            "Reference endpoints are immutable; remove this reference and create a new one.",
        )
    ref.sort_order = payload.sort_order
    ref.is_active = payload.is_active
    ref.metadata_json = payload.metadata_json
    await db.flush()
    ref = await _get_atomic_ref_or_404(ref.id, db)
    return _serialize_atomic_ref(ref)


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
    if is_legacy_executable_activity(payload):
        raise _domain_error(
            422,
            "LEGACY_EXECUTABLE_CREATE_FORBIDDEN",
            "ActivityNode(level=3) has been sunset; create an AtomicActivity and package reference.",
        )
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
    if is_legacy_executable_activity(obj) or is_legacy_executable_activity(payload):
        raise _domain_error(
            422,
            "LEGACY_EXECUTABLE_READ_ONLY",
            "Historical ActivityNode(level=3) rows are read-only.",
        )
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
    obj.description = payload.description
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
    if is_atomic_state(payload):
        if payload.parent_id is not None:
            raise _domain_error(
                422,
                "ATOMIC_STATE_PARENT_FORBIDDEN",
                "Atomic state bodies cannot have parent_id; create a StateNodeReference membership instead.",
            )
    else:
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
    if is_atomic_state(payload):
        if payload.parent_id is not None:
            raise _domain_error(
                422,
                "ATOMIC_STATE_PARENT_FORBIDDEN",
                "Atomic state bodies cannot have parent_id; create a StateNodeReference membership instead.",
            )
    else:
        await _validate_state_parent(
            db,
            obj.machine_type_id,
            payload.level,
            payload.parent_id,
            current_id=node_id,
        )
    await _validate_state_node_payload(
        db,
        obj.machine_type_id,
        payload,
        has_children=bool(obj.children),
        current_id=node_id,
    )
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
    reference_count = int(
        (await db.execute(
            select(func.count(StateNodeReference.id)).where(
                StateNodeReference.state_node_id == node_id
            )
        )).scalar_one()
    )
    binding_count = int(
        (await db.execute(
            select(func.count(ActivityStateBinding.id)).where(
                ActivityStateBinding.state_node_id == node_id
            )
        )).scalar_one()
    )
    dependencies = {
        "child_packages": len(obj.children),
        "package_references": reference_count,
        "state_bindings": binding_count,
        "scope_guard_preconditions": len(obj.scope_guard_preconditions),
    }
    if any(dependencies.values()):
        raise _domain_error(
            409,
            "BODY_IN_USE",
            "State body is still referenced; remove its relationships before deleting the body.",
            dependencies=dependencies,
        )
    await db.delete(obj)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/machine-types/{machine_type_id}/state-node-references",
    response_model=list[StateNodeReferenceResponse],
)
async def list_state_node_references(
    machine_type_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    await _get_machine_type_or_404(machine_type_id, db)
    result = await db.execute(
        select(StateNodeReference)
        .join(StateNodeReference.state_node)
        .where(StateNode.machine_type_id == machine_type_id)
        .options(
            selectinload(StateNodeReference.state_node),
            selectinload(StateNodeReference.parent_state_node),
        )
        .order_by(StateNodeReference.parent_state_node_id, StateNodeReference.sort_order, StateNodeReference.id)
    )
    return [_serialize_state_node_reference(item) for item in result.scalars().all()]


@router.post(
    "/state-nodes/{node_id}/references",
    response_model=StateNodeReferenceResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_state_node_reference(
    node_id: int,
    payload: StateNodeReferenceCreate,
    db: AsyncSession = Depends(get_db_session),
):
    state_node = await _get_state_node_or_404(node_id, db)
    parent_state_node = await _get_state_node_or_404(payload.parent_state_node_id, db)
    await _validate_state_reference(db, state_node, parent_state_node)

    ref = StateNodeReference(
        state_node_id=node_id,
        parent_state_node_id=payload.parent_state_node_id,
        sort_order=payload.sort_order,
        is_active=payload.is_active,
        metadata_json=payload.metadata_json,
    )
    db.add(ref)
    await db.flush()
    ref = await _get_state_node_reference_or_404(ref.id, db)
    return _serialize_state_node_reference(ref)


@router.put("/state-node-references/{ref_id}", response_model=StateNodeReferenceResponse)
async def update_state_node_reference(
    ref_id: int,
    payload: StateNodeReferenceUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    ref = await _get_state_node_reference_or_404(ref_id, db)
    if (
        payload.state_node_id is not None
        and payload.state_node_id != ref.state_node_id
    ) or (
        payload.parent_state_node_id is not None
        and payload.parent_state_node_id != ref.parent_state_node_id
    ):
        raise _domain_error(
            409,
            "RELATION_ENDPOINT_IMMUTABLE",
            "Reference endpoints are immutable; remove this reference and create a new one.",
        )
    ref.sort_order = payload.sort_order
    ref.is_active = payload.is_active
    ref.metadata_json = payload.metadata_json
    await db.flush()
    ref = await _get_state_node_reference_or_404(ref.id, db)
    return _serialize_state_node_reference(ref)


@router.delete("/state-node-references/{ref_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_state_node_reference(ref_id: int, db: AsyncSession = Depends(get_db_session)):
    ref = await _get_state_node_reference_or_404(ref_id, db)
    await db.delete(ref)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/machine-types/{machine_type_id}/activity-state-bindings",
    response_model=list[ActivityStateBindingResponse],
)
async def list_activity_state_bindings(
    machine_type_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    await _get_machine_type_or_404(machine_type_id, db)
    result = await db.execute(
        select(ActivityStateBinding)
        .where(ActivityStateBinding.machine_type_id == machine_type_id)
        .options(
            selectinload(ActivityStateBinding.activity_node),
            selectinload(ActivityStateBinding.atomic_activity),
            selectinload(ActivityStateBinding.op_rule),
            selectinload(ActivityStateBinding.state_node),
        )
        .order_by(ActivityStateBinding.id)
    )
    return [await _serialize_activity_state_binding(item, db) for item in result.scalars().all()]


@router.post(
    "/activity-state-bindings",
    response_model=ActivityStateBindingResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_activity_state_binding(
    payload: ActivityStateBindingCreate,
    db: AsyncSession = Depends(get_db_session),
):
    activity_node, atomic_activity, op_rule, _, binding_type, covered_leaf_ids, coverage_status = (
        await _resolve_binding_payload(db, payload)
    )
    binding = ActivityStateBinding(
        machine_type_id=payload.machine_type_id,
        activity_node_id=activity_node.id if activity_node else None,
        atomic_activity_id=atomic_activity.id if atomic_activity else None,
        op_rule_id=op_rule.id if op_rule else None,
        state_node_id=payload.state_node_id,
        binding_role=payload.binding_role,
        binding_type=binding_type,
        coverage_policy="snapshot",
        covered_leaf_state_ids=covered_leaf_ids,
        coverage_status=coverage_status,
        is_inherited=payload.is_inherited,
        is_active=payload.is_active,
        metadata_json=payload.metadata_json,
    )
    db.add(binding)
    await db.flush()
    await _sync_binding_rule_facts(binding, db)
    await db.flush()
    binding = await _get_activity_state_binding_or_404(binding.id, db)
    return await _serialize_activity_state_binding(binding, db)


@router.put("/activity-state-bindings/{binding_id}", response_model=ActivityStateBindingResponse)
async def update_activity_state_binding(
    binding_id: int,
    payload: ActivityStateBindingUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    binding = await _get_activity_state_binding_or_404(binding_id, db)
    if payload.machine_type_id != binding.machine_type_id:
        raise HTTPException(status_code=422, detail="Activity-state binding machine_type_id cannot be changed")
    activity_node, atomic_activity, op_rule, _, binding_type, covered_leaf_ids, coverage_status = (
        await _resolve_binding_payload(db, payload)
    )
    endpoint_changed = (
        (activity_node.id if activity_node else None) != binding.activity_node_id
        or (atomic_activity.id if atomic_activity else None) != binding.atomic_activity_id
        or (op_rule.id if op_rule else None) != binding.op_rule_id
        or payload.state_node_id != binding.state_node_id
        or payload.binding_role != binding.binding_role
    )
    if endpoint_changed:
        raise _domain_error(
            409,
            "RELATION_ENDPOINT_IMMUTABLE",
            "Binding endpoints and role are immutable; delete the old binding and create a new one.",
        )
    old_op_rule_id = binding.op_rule_id
    old_binding_role = binding.binding_role
    old_managed_keys = _binding_managed_rule_fact_keys(binding, old_binding_role)
    binding.machine_type_id = payload.machine_type_id
    binding.activity_node_id = activity_node.id if activity_node else None
    binding.atomic_activity_id = atomic_activity.id if atomic_activity else None
    binding.op_rule_id = op_rule.id if op_rule else None
    binding.state_node_id = payload.state_node_id
    binding.binding_role = payload.binding_role
    binding.binding_type = binding_type
    binding.coverage_policy = "snapshot"
    binding.covered_leaf_state_ids = covered_leaf_ids
    binding.coverage_status = coverage_status
    binding.is_inherited = payload.is_inherited
    binding.is_active = payload.is_active
    binding.metadata_json = payload.metadata_json
    await db.flush()
    await _sync_binding_rule_facts(
        binding,
        db,
        previous_managed_keys=(
            old_managed_keys
            if binding.op_rule_id == old_op_rule_id and binding.binding_role == old_binding_role
            else set()
        ),
    )
    await _reconcile_rule_binding_facts(
        db,
        old_op_rule_id,
        old_binding_role,
        stale_keys=old_managed_keys,
    )
    await db.flush()
    binding = await _get_activity_state_binding_or_404(binding_id, db)
    return await _serialize_activity_state_binding(binding, db)


@router.delete("/activity-state-bindings/{binding_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_activity_state_binding(
    binding_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    binding = await _get_activity_state_binding_or_404(binding_id, db)
    old_op_rule_id = binding.op_rule_id
    old_binding_role = binding.binding_role
    old_managed_keys = _binding_managed_rule_fact_keys(binding, old_binding_role)
    await db.delete(binding)
    await db.flush()
    await _reconcile_rule_binding_facts(
        db,
        old_op_rule_id,
        old_binding_role,
        stale_keys=old_managed_keys,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/activity-state-bindings/{binding_id}/refresh-coverage",
    response_model=ActivityStateBindingResponse,
)
async def refresh_activity_state_binding_coverage(
    binding_id: int,
    db: AsyncSession = Depends(get_db_session),
):
    binding = await _get_activity_state_binding_or_404(binding_id, db)
    old_managed_keys = _binding_managed_rule_fact_keys(binding, binding.binding_role)
    covered_leaf_ids = await _resolve_covered_leaf_ids(db, binding.state_node, None)
    binding.covered_leaf_state_ids = covered_leaf_ids
    binding.coverage_status = "complete"
    nodes = await _load_state_nodes_for_machine(db, binding.machine_type_id)
    references = await _load_state_references_for_machine(db, binding.machine_type_id)
    binding.coverage_status = _compute_coverage_status(binding, nodes, references)
    await db.flush()
    await _sync_binding_rule_facts(binding, db, previous_managed_keys=old_managed_keys)
    await _reconcile_rule_binding_facts(
        db,
        binding.op_rule_id,
        binding.binding_role,
        stale_keys=old_managed_keys,
    )
    await db.flush()
    binding = await _get_activity_state_binding_or_404(binding_id, db)
    return await _serialize_activity_state_binding(binding, db)


@router.get("/activity-nodes/{activity_node_id}/scope-guards", response_model=list[ScopeGuardResponse])
async def list_scope_guards(activity_node_id: int, db: AsyncSession = Depends(get_db_session)):
    raise _domain_error(
        410,
        "SCOPE_GUARD_SUNSET",
        "Scope Guard is available only through the read-only audit endpoint.",
        audit_endpoint=f"/api/v1/audit/activity-nodes/{activity_node_id}/scope-guards",
    )


@router.get(
    "/audit/activity-nodes/{activity_node_id}/scope-guards",
    response_model=list[ScopeGuardResponse],
)
async def audit_scope_guards(activity_node_id: int, db: AsyncSession = Depends(get_db_session)):
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
    raise _domain_error(
        410,
        "SCOPE_GUARD_SUNSET",
        "Scope Guard has been sunset; model admission conditions as atomic-activity input bindings.",
    )


@router.put("/scope-guards/{guard_id}", response_model=ScopeGuardResponse)
async def update_scope_guard(
    guard_id: int,
    payload: ScopeGuardUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    raise _domain_error(
        410,
        "SCOPE_GUARD_SUNSET",
        "Scope Guard has been sunset; existing rows are audit-only.",
    )


@router.delete("/scope-guards/{guard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scope_guard(guard_id: int, db: AsyncSession = Depends(get_db_session)):
    raise _domain_error(
        410,
        "SCOPE_GUARD_SUNSET",
        "Scope Guard has been sunset; existing rows are audit-only.",
    )


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


@router.post(
    "/machine-types/{machine_type_id}/network-editor/graph",
    response_model=NetworkEditorGraphResponse,
)
async def preview_network_editor_graph(
    machine_type_id: int,
    payload: NetworkEditorRequest,
    db: AsyncSession = Depends(get_db_session),
):
    await _get_machine_type_or_404(machine_type_id, db)
    return await project_network_editor_graph(db, machine_type_id, payload)


@router.post(
    "/machine-types/{machine_type_id}/network-editor/validate",
    response_model=NetworkEditorValidationResponse,
)
async def validate_network_editor(
    machine_type_id: int,
    payload: NetworkEditorRequest,
    db: AsyncSession = Depends(get_db_session),
):
    await _get_machine_type_or_404(machine_type_id, db)
    return await validate_network_editor_model(db, machine_type_id, payload)


@router.post(
    "/machine-types/{machine_type_id}/network-editor/impact",
    response_model=NetworkEditorImpactResponse,
)
async def analyze_network_editor_impact_endpoint(
    machine_type_id: int,
    payload: NetworkEditorImpactRequest,
    db: AsyncSession = Depends(get_db_session),
):
    await _get_machine_type_or_404(machine_type_id, db)
    if bool(payload.state_node_id) == bool(payload.activity_graph_id):
        raise HTTPException(status_code=422, detail="Select exactly one state_node_id or activity_graph_id")
    result = await analyze_network_editor_impact(db, machine_type_id, payload)
    if result["status"] == "not_found":
        raise HTTPException(status_code=404, detail="Selected network editor node was not found")
    return result


@router.post(
    "/machine-types/{machine_type_id}/network-editor/solver-precheck",
    response_model=NetworkEditorSolverPrecheckResponse,
)
async def precheck_network_editor_solver_endpoint(
    machine_type_id: int,
    payload: NetworkEditorRequest,
    db: AsyncSession = Depends(get_db_session),
):
    await _get_machine_type_or_404(machine_type_id, db)
    return await precheck_network_editor_solver(db, machine_type_id, payload)


@router.post(
    "/machine-types/{machine_type_id}/network-editor/export-preview",
    response_model=NetworkEditorExportPreviewResponse,
    deprecated=True,
)
async def preview_network_editor_export_endpoint(
    machine_type_id: int,
    payload: NetworkEditorRequest,
    db: AsyncSession = Depends(get_db_session),
):
    return await precheck_network_editor_solver_endpoint(machine_type_id, payload, db)


def _commit_result(change_index: int, change_type: str, operation: str, result: Any = None) -> dict[str, Any]:
    if hasattr(result, "model_dump"):
        payload = result.model_dump()
    elif isinstance(result, Response):
        payload = None
    else:
        payload = result
    return {
        "index": change_index,
        "entity_type": change_type,
        "operation": operation,
        "result": payload,
    }


def _draft_result_id(result: Any) -> Optional[int]:
    if hasattr(result, "model_dump"):
        result = result.model_dump()
    if isinstance(result, dict):
        raw_id = result.get("id")
        return _coerce_network_editor_int(raw_id, "draft_result.id") if raw_id is not None else None
    raw_id = getattr(result, "id", None)
    return _coerce_network_editor_int(raw_id, "draft_result.id") if raw_id is not None else None


def _coerce_network_editor_int(value: Any, field_name: str, *, default: Optional[int] = None) -> Optional[int]:
    if value is None:
        return default
    if isinstance(value, dict):
        if "_draft_ref" in value:
            raise HTTPException(status_code=422, detail=f"{field_name} contains an unresolved draft reference")
        candidate_keys = ["id"]
        if field_name.endswith("state_node_id"):
            candidate_keys.insert(0, "state_node_id")
        if field_name.endswith("covered_leaf_state_ids"):
            candidate_keys.insert(0, "state_node_id")
        if field_name.endswith("activity_node_id") or field_name.endswith("package_id"):
            candidate_keys.insert(0, "activity_node_id")
            candidate_keys.insert(0, "package_id")
        if field_name.endswith("atomic_activity_id"):
            candidate_keys.insert(0, "atomic_activity_id")
        if field_name.endswith("sort_order"):
            candidate_keys.insert(0, "sort_order")
        for key in candidate_keys:
            candidate = value.get(key)
            if candidate is not None and not isinstance(candidate, (dict, list)):
                return _coerce_network_editor_int(candidate, field_name, default=default)
        raise HTTPException(status_code=422, detail=f"{field_name} must be an integer id, not an object")
    if isinstance(value, str):
        graph_match = re.match(r"^(?:state_node|activity_node|atomic_activity):(\d+)(?::.*)?$", value)
        if graph_match:
            return int(graph_match.group(1))
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"{field_name} must be an integer id") from exc


def _store_network_editor_draft_ref(
    draft_refs: dict[str, dict[str, Any]],
    client_id: Optional[str],
    entity_type: str,
    result: Any,
) -> None:
    if not client_id:
        return
    result_id = _draft_result_id(result)
    if result_id is None:
        return
    draft_refs[client_id] = {
        "entity_type": entity_type,
        "id": result_id,
        "result": result,
    }


def _resolve_network_editor_draft_ref(
    value: Any,
    draft_refs: dict[str, dict[str, Any]],
    *,
    expected_entity_type: str,
    field_name: str,
) -> Any:
    if not isinstance(value, dict) or "_draft_ref" not in value:
        return value
    ref_id = value.get("_draft_ref")
    if not isinstance(ref_id, str) or not ref_id:
        raise HTTPException(status_code=422, detail=f"{field_name} _draft_ref must be a non-empty string")
    ref = draft_refs.get(ref_id)
    if ref is None:
        raise HTTPException(status_code=422, detail=f"{field_name} references unknown draft change {ref_id}")
    if ref.get("entity_type") != expected_entity_type:
        raise HTTPException(
            status_code=422,
            detail=f"{field_name} expected {expected_entity_type} draft ref, got {ref.get('entity_type')}",
        )
    return ref["id"]


def _resolve_network_editor_binding_refs(payload: dict[str, Any], draft_refs: dict[str, dict[str, Any]]) -> None:
    if "state_node_id" in payload:
        payload["state_node_id"] = _resolve_network_editor_draft_ref(
            payload["state_node_id"],
            draft_refs,
            expected_entity_type="state_node",
            field_name="state_node_id",
        )
        payload["state_node_id"] = _coerce_network_editor_int(payload["state_node_id"], "activity_state_binding.state_node_id")
    if "activity_node_id" in payload:
        payload["activity_node_id"] = _resolve_network_editor_draft_ref(
            payload["activity_node_id"],
            draft_refs,
            expected_entity_type="activity_node",
            field_name="activity_node_id",
        )
        payload["activity_node_id"] = _coerce_network_editor_int(payload["activity_node_id"], "activity_state_binding.activity_node_id")
    if "atomic_activity_id" in payload:
        payload["atomic_activity_id"] = _resolve_network_editor_draft_ref(
            payload["atomic_activity_id"],
            draft_refs,
            expected_entity_type="atomic_activity",
            field_name="atomic_activity_id",
        )
        payload["atomic_activity_id"] = _coerce_network_editor_int(payload["atomic_activity_id"], "activity_state_binding.atomic_activity_id")
    if "op_rule_id" in payload:
        payload["op_rule_id"] = _resolve_network_editor_draft_ref(
            payload["op_rule_id"],
            draft_refs,
            expected_entity_type="op_rule",
            field_name="op_rule_id",
        )
        payload["op_rule_id"] = _coerce_network_editor_int(payload["op_rule_id"], "activity_state_binding.op_rule_id")
    if "covered_leaf_state_ids" in payload and isinstance(payload["covered_leaf_state_ids"], list):
        payload["covered_leaf_state_ids"] = [
            _coerce_network_editor_int(
                _resolve_network_editor_draft_ref(
                    state_id,
                    draft_refs,
                    expected_entity_type="state_node",
                    field_name="covered_leaf_state_ids",
                ),
                "activity_state_binding.covered_leaf_state_ids",
            )
            for state_id in payload["covered_leaf_state_ids"]
        ]


def _resolve_network_editor_state_refs(payload: dict[str, Any], draft_refs: dict[str, dict[str, Any]]) -> None:
    if "parent_id" in payload:
        payload["parent_id"] = _resolve_network_editor_draft_ref(
            payload["parent_id"],
            draft_refs,
            expected_entity_type="state_node",
            field_name="parent_id",
        )
        payload["parent_id"] = _coerce_network_editor_int(payload["parent_id"], "state_node.parent_id")


def _resolve_network_editor_state_reference_refs(payload: dict[str, Any], draft_refs: dict[str, dict[str, Any]]) -> None:
    if "state_node_id" in payload:
        payload["state_node_id"] = _resolve_network_editor_draft_ref(
            payload["state_node_id"],
            draft_refs,
            expected_entity_type="state_node",
            field_name="state_node_id",
        )
        payload["state_node_id"] = _coerce_network_editor_int(payload["state_node_id"], "state_node_reference.state_node_id")
    if "parent_state_node_id" in payload:
        payload["parent_state_node_id"] = _resolve_network_editor_draft_ref(
            payload["parent_state_node_id"],
            draft_refs,
            expected_entity_type="state_node",
            field_name="parent_state_node_id",
        )
        payload["parent_state_node_id"] = _coerce_network_editor_int(
            payload["parent_state_node_id"],
            "state_node_reference.parent_state_node_id",
        )


def _resolve_network_editor_state_package_fork_refs(payload: dict[str, Any], draft_refs: dict[str, dict[str, Any]]) -> None:
    added_state = payload.get("added_state")
    if not isinstance(added_state, dict):
        return
    if str(added_state.get("mode") or "").lower() != "reuse":
        return
    if "state_node_id" in added_state:
        added_state["state_node_id"] = _resolve_network_editor_draft_ref(
            added_state["state_node_id"],
            draft_refs,
            expected_entity_type="state_node",
            field_name="added_state.state_node_id",
        )


def _resolve_network_editor_activity_refs(payload: dict[str, Any], draft_refs: dict[str, dict[str, Any]]) -> None:
    if "parent_id" in payload:
        payload["parent_id"] = _resolve_network_editor_draft_ref(
            payload["parent_id"],
            draft_refs,
            expected_entity_type="activity_node",
            field_name="parent_id",
        )
        payload["parent_id"] = _coerce_network_editor_int(payload["parent_id"], "activity_node.parent_id")


def _resolve_network_editor_atomic_refs(payload: dict[str, Any], draft_refs: dict[str, dict[str, Any]]) -> None:
    if "package_id" in payload:
        payload["package_id"] = _resolve_network_editor_draft_ref(
            payload["package_id"],
            draft_refs,
            expected_entity_type="activity_node",
            field_name="package_id",
        )
        payload["package_id"] = _coerce_network_editor_int(payload["package_id"], "atomic_activity.package_id")


def _resolve_network_editor_package_ref_refs(payload: dict[str, Any], draft_refs: dict[str, dict[str, Any]]) -> None:
    if "package_id" in payload:
        payload["package_id"] = _resolve_network_editor_draft_ref(
            payload["package_id"],
            draft_refs,
            expected_entity_type="activity_node",
            field_name="package_id",
        )
        payload["package_id"] = _coerce_network_editor_int(payload["package_id"], "activity_package_atomic_ref.package_id")
    if "atomic_activity_id" in payload:
        payload["atomic_activity_id"] = _resolve_network_editor_draft_ref(
            payload["atomic_activity_id"],
            draft_refs,
            expected_entity_type="atomic_activity",
            field_name="atomic_activity_id",
        )
        payload["atomic_activity_id"] = _coerce_network_editor_int(
            payload["atomic_activity_id"],
            "activity_package_atomic_ref.atomic_activity_id",
        )


def _resolve_network_editor_rule_refs(payload: dict[str, Any], draft_refs: dict[str, dict[str, Any]]) -> None:
    if "activity_node_id" in payload:
        payload["activity_node_id"] = _resolve_network_editor_draft_ref(
            payload["activity_node_id"],
            draft_refs,
            expected_entity_type="activity_node",
            field_name="activity_node_id",
        )
        payload["activity_node_id"] = _coerce_network_editor_int(payload["activity_node_id"], "op_rule.activity_node_id")
    if "atomic_activity_id" in payload:
        payload["atomic_activity_id"] = _resolve_network_editor_draft_ref(
            payload["atomic_activity_id"],
            draft_refs,
            expected_entity_type="atomic_activity",
            field_name="atomic_activity_id",
        )
        payload["atomic_activity_id"] = _coerce_network_editor_int(payload["atomic_activity_id"], "op_rule.atomic_activity_id")


async def _state_has_membership(
    session: AsyncSession,
    state_node_id: int,
    parent_state_node_id: int,
) -> bool:
    state = await _get_state_node_or_404(state_node_id, session)
    if state.parent_id == parent_state_node_id:
        return True
    result = await session.execute(
        select(StateNodeReference.id).where(
            StateNodeReference.state_node_id == state_node_id,
            StateNodeReference.parent_state_node_id == parent_state_node_id,
            StateNodeReference.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none() is not None


def _state_node_dimension_template_key(node: StateNode) -> Optional[str]:
    metadata_key = _dimension_template_key_from_metadata(node.metadata_json)
    if metadata_key:
        return metadata_key
    feature_key = str(node.feature_key or "")
    if "__" not in feature_key:
        return None
    candidate = feature_key.split("__", 1)[0]
    return candidate if _is_dimension_template_key(candidate) else None


async def _find_exact_state_object_match(
    session: AsyncSession,
    machine_type_id: int,
    payload: StateNodeCreate,
) -> Optional[StateNode]:
    template_key = _dimension_template_key_from_metadata(payload.metadata_json)
    if not template_key or payload.state_kind == "aggregate" or not payload.feature_key or not payload.target_value:
        return None
    result = await session.execute(
        select(StateNode).where(
            StateNode.machine_type_id == machine_type_id,
            StateNode.state_kind != "aggregate",
            StateNode.feature_key.is_not(None),
            StateNode.target_value == payload.target_value,
        )
    )
    normalized_name = str(payload.name or "").strip().lower()
    for node in result.scalars():
        if str(node.name or "").strip().lower() != normalized_name:
            continue
        if str(node.feature_key or "") != str(payload.feature_key or ""):
            continue
        if _state_node_dimension_template_key(node) == template_key:
            return node
    return None


async def _reuse_exact_state_object_for_create(
    machine_type_id: int,
    payload: StateNodeCreate,
    db: AsyncSession,
) -> Optional[dict[str, Any]]:
    candidate = await _find_exact_state_object_match(db, machine_type_id, payload)
    if candidate is None:
        return None
    parent_id = payload.parent_id
    reuse_result = _serialize_state_node(candidate)
    if parent_id and not await _state_has_membership(db, candidate.id, parent_id):
        ref_result = await create_state_node_reference(
            candidate.id,
            StateNodeReferenceCreate(
                parent_state_node_id=parent_id,
                sort_order=payload.sort_order,
                is_active=payload.is_active,
                metadata_json={
                    "_network_editor_reuse": {
                        "source": "exact_state_object_match",
                        "requested_name": payload.name,
                        "dimension_template_key": _dimension_template_key_from_metadata(payload.metadata_json),
                        "target_value": payload.target_value,
                    }
                },
            ),
            db,
        )
        reuse_result["_network_editor_reuse_reference"] = ref_result
    else:
        reuse_result["_network_editor_reuse_reference"] = None
    return reuse_result


def _is_network_editor_atomic_state_create(payload: StateNodeCreate) -> bool:
    return (
        payload.state_kind != "aggregate"
        and bool(payload.feature_key)
        and payload.target_value is not None
    )


def _metadata_without_network_editor_layout(metadata: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if not metadata:
        return metadata
    next_metadata = dict(metadata)
    next_metadata.pop("_network_editor_layout", None)
    return next_metadata or None


async def _create_network_editor_atomic_state_library_object(
    machine_type_id: int,
    payload: StateNodeCreate,
    db: AsyncSession,
) -> dict[str, Any]:
    parent_id = payload.parent_id
    if parent_id is None or not _is_network_editor_atomic_state_create(payload):
        result = await _reuse_exact_state_object_for_create(machine_type_id, payload, db)
        if result is None:
            result = await create_state_node(machine_type_id, payload, db)
        return result

    reference_layout = (payload.metadata_json or {}).get("_network_editor_layout")
    library_payload = payload.model_copy(
        update={
            "parent_id": None,
            "level": 1,
            "metadata_json": _metadata_without_network_editor_layout(payload.metadata_json),
        }
    )
    result = await _reuse_exact_state_object_for_create(machine_type_id, library_payload, db)
    if result is None:
        result = await create_state_node(machine_type_id, library_payload, db)

    state_node_id = _coerce_network_editor_int(result["id"], "state_node.result.id")
    if not await _state_has_membership(db, state_node_id, parent_id):
        reference_metadata: dict[str, Any] = {
            "_network_editor_reuse": {
                "source": "atomic_state_library_create",
                "requested_name": payload.name,
                "target_value": payload.target_value,
            }
        }
        if reference_layout:
            reference_metadata["_network_editor_layout"] = reference_layout
        result["_network_editor_created_reference"] = await create_state_node_reference(
            state_node_id,
            StateNodeReferenceCreate(
                parent_state_node_id=parent_id,
                sort_order=payload.sort_order,
                is_active=payload.is_active,
                metadata_json=reference_metadata,
            ),
            db,
        )
    else:
        result["_network_editor_created_reference"] = None
    return result


async def _create_state_package_fork(
    machine_type_id: int,
    payload: dict[str, Any],
    db: AsyncSession,
) -> dict[str, Any]:
    source_state_node_id = payload.get("source_state_node_id")
    current_parent_state_node_id = payload.get("current_parent_state_node_id")
    if not source_state_node_id or not current_parent_state_node_id:
        raise HTTPException(
            status_code=422,
            detail="state_package_fork requires source_state_node_id and current_parent_state_node_id",
        )

    source = await _get_state_node_or_404(
        _coerce_network_editor_int(source_state_node_id, "state_package_fork.source_state_node_id"),
        db,
    )
    current_parent = await _get_state_node_or_404(
        _coerce_network_editor_int(current_parent_state_node_id, "state_package_fork.current_parent_state_node_id"),
        db,
    )
    if source.machine_type_id != machine_type_id or current_parent.machine_type_id != machine_type_id:
        raise HTTPException(status_code=422, detail="Forked state packages must belong to the same machine type")
    if source.feature_key or source.state_kind != "aggregate":
        raise HTTPException(status_code=422, detail="Only aggregate state packages can be forked")
    if current_parent.id == source.id:
        raise HTTPException(status_code=422, detail="Fork parent cannot be the source state package")

    branch_payload = dict(payload.get("branch") or {})
    branch_name = str(branch_payload.get("name") or "").strip()
    branch_reason = str(payload.get("reason") or branch_payload.get("reason") or "").strip()
    if not branch_name:
        raise HTTPException(status_code=422, detail="state_package_fork requires branch.name")
    if not branch_reason:
        raise HTTPException(status_code=422, detail="state_package_fork requires a branch reason")
    branch_metadata = dict(branch_payload.get("metadata_json") or {})
    branch_metadata["_network_editor_branch"] = {
        "source_state_node_id": source.id,
        "source_state_node_code": source.code,
        "source_state_node_name": source.name,
        "current_parent_state_node_id": current_parent.id,
        "reason": branch_reason,
    }
    branch = await create_state_node(
        machine_type_id,
        StateNodeCreate(
            machine_type_id=machine_type_id,
            parent_id=current_parent.id,
            level=current_parent.level + 1,
            code=branch_payload.get("code"),
            name=branch_name,
            feature_key=None,
            operator="eq",
            target_value=None,
            state_kind="aggregate",
            sort_order=_coerce_network_editor_int(
                branch_payload.get("sort_order") or source.sort_order,
                "state_package_fork.branch.sort_order",
                default=0,
            ),
            is_active=bool(branch_payload.get("is_active", True)),
            metadata_json=branch_metadata,
        ),
        db,
    )
    branch_id = _coerce_network_editor_int(branch["id"], "state_package_fork.branch.id")

    nodes = await _load_state_nodes_for_machine(db, machine_type_id)
    refs = await _load_state_references_for_machine(db, machine_type_id)
    direct_member_ids: list[int] = []
    seen_members: set[int] = set()
    for node in nodes:
        if node.parent_id == source.id and node.id not in seen_members:
            direct_member_ids.append(node.id)
            seen_members.add(node.id)
    for ref in refs:
        if ref.is_active and ref.parent_state_node_id == source.id and ref.state_node_id not in seen_members:
            direct_member_ids.append(ref.state_node_id)
            seen_members.add(ref.state_node_id)

    removed_state_node_id = payload.get("removed_state_node_id")
    if removed_state_node_id is not None:
        removed_state_node_id = _coerce_network_editor_int(
            removed_state_node_id,
            "state_package_fork.removed_state_node_id",
        )
        if removed_state_node_id not in seen_members:
            raise HTTPException(status_code=422, detail="removed_state_node_id is not a direct member of the source package")
    copied_reference_count = 0
    for member_id in direct_member_ids:
        if removed_state_node_id is not None and member_id == removed_state_node_id:
            continue
        if member_id == branch_id or await _state_has_membership(db, member_id, branch_id):
            continue
        await create_state_node_reference(
            member_id,
            StateNodeReferenceCreate(
                parent_state_node_id=branch_id,
                sort_order=0,
                is_active=True,
                metadata_json={"_network_editor_branch_copy": {"source_state_node_id": source.id}},
            ),
            db,
        )
        copied_reference_count += 1

    added_state_result: dict[str, Any] | None = None
    added_state = dict(payload.get("added_state") or {})
    added_mode = str(added_state.get("mode") or "").lower()
    if added_mode == "create":
        state_payload = dict(added_state.get("payload") or {})
        state_payload["machine_type_id"] = machine_type_id
        state_payload["parent_id"] = branch_id
        state_payload["level"] = current_parent.level + 2
        added_state_result = await create_state_node(machine_type_id, StateNodeCreate(**state_payload), db)
    elif added_mode == "reuse":
        added_state_node_id = added_state.get("state_node_id")
        if not added_state_node_id:
            raise HTTPException(status_code=422, detail="state_package_fork reuse requires added_state.state_node_id")
        added_node = await _get_state_node_or_404(
            _coerce_network_editor_int(added_state_node_id, "state_package_fork.added_state.state_node_id"),
            db,
        )
        if added_node.machine_type_id != machine_type_id:
            raise HTTPException(status_code=422, detail="Reused state must belong to the same machine type")
        if not await _state_has_membership(db, added_node.id, branch_id):
            added_ref = await create_state_node_reference(
                added_node.id,
                StateNodeReferenceCreate(
                    parent_state_node_id=branch_id,
                    sort_order=_coerce_network_editor_int(
                        added_state.get("sort_order"),
                        "state_package_fork.added_state.sort_order",
                        default=0,
                    ),
                    is_active=True,
                    metadata_json={"_network_editor_reuse": added_state.get("metadata_json") or {}},
                ),
                db,
            )
            added_state_result = added_ref
        else:
            added_state_result = _serialize_state_node(added_node)
    elif added_mode:
        raise HTTPException(status_code=422, detail=f"Unsupported state_package_fork added_state mode: {added_mode}")

    removed_reference_id = None
    replace_reference_id = payload.get("replace_reference_id")
    if replace_reference_id:
        ref = await _get_state_node_reference_or_404(
            _coerce_network_editor_int(replace_reference_id, "state_package_fork.replace_reference_id"),
            db,
        )
        if ref.state_node_id != source.id or ref.parent_state_node_id != current_parent.id:
            raise HTTPException(status_code=422, detail="replace_reference_id does not match the fork source and parent")
        await delete_state_node_reference(ref.id, db)
        removed_reference_id = ref.id

    return {
        "branch": branch,
        "added_state": added_state_result,
        "removed_state_node_id": removed_state_node_id,
        "copied_reference_count": copied_reference_count,
        "removed_reference_id": removed_reference_id,
    }


async def _apply_network_editor_commit_change(
    machine_type_id: int,
    index: int,
    change: Any,
    db: AsyncSession,
    draft_refs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    entity_type = change.entity_type.strip().lower()
    operation = change.operation.strip().lower()
    payload = dict(change.payload or {})
    entity_id = change.entity_id

    try:
        if entity_type == "state_node":
            _resolve_network_editor_state_refs(payload, draft_refs)
            if operation == "create":
                state_payload = StateNodeCreate(**payload)
                result = await _create_network_editor_atomic_state_library_object(machine_type_id, state_payload, db)
                _store_network_editor_draft_ref(draft_refs, change.client_id, entity_type, result)
            elif operation == "update":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="state_node update requires entity_id")
                result = await update_state_node(entity_id, StateNodeUpdate(**payload), db)
            elif operation == "delete":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="state_node delete requires entity_id")
                result = await delete_state_node(entity_id, db)
            else:
                raise HTTPException(status_code=422, detail=f"Unsupported state_node operation: {operation}")
            return _commit_result(index, entity_type, operation, result)

        if entity_type == "activity_node":
            _resolve_network_editor_activity_refs(payload, draft_refs)
            if operation == "create":
                result = await create_activity_node(machine_type_id, ActivityNodeCreate(**payload), db)
                _store_network_editor_draft_ref(draft_refs, change.client_id, entity_type, result)
            elif operation == "update":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="activity_node update requires entity_id")
                result = await update_activity_node(entity_id, ActivityNodeUpdate(**payload), db)
            elif operation == "delete":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="activity_node delete requires entity_id")
                result = await delete_activity_node(entity_id, db)
            else:
                raise HTTPException(status_code=422, detail=f"Unsupported activity_node operation: {operation}")
            return _commit_result(index, entity_type, operation, result)

        if entity_type == "atomic_activity":
            _resolve_network_editor_atomic_refs(payload, draft_refs)
            package_id = payload.pop("package_id", None)
            package_ref_metadata_json = payload.pop("package_ref_metadata_json", None)
            package_ref_sort_order = payload.pop("package_ref_sort_order", None)
            if operation == "create":
                if package_id and package_ref_metadata_json is not None and isinstance(payload.get("metadata_json"), dict):
                    atomic_metadata = dict(payload["metadata_json"])
                    atomic_metadata.pop("_network_editor_layout", None)
                    payload["metadata_json"] = atomic_metadata or None
                result = await create_atomic_activity(machine_type_id, AtomicActivityCreate(**payload), db)
                _store_network_editor_draft_ref(draft_refs, change.client_id, entity_type, result)
                if package_id:
                    if package_ref_metadata_json is None:
                        atomic_metadata = payload.get("metadata_json")
                        if isinstance(atomic_metadata, dict) and "_network_editor_layout" in atomic_metadata:
                            package_ref_metadata_json = {
                                "_network_editor_layout": atomic_metadata["_network_editor_layout"],
                            }
                    await create_activity_package_atomic_ref(
                        _coerce_network_editor_int(package_id, "atomic_activity.package_id"),
                        ActivityPackageAtomicRefCreate(
                            atomic_activity_id=_coerce_network_editor_int(result["id"], "atomic_activity.result.id"),
                            sort_order=_coerce_network_editor_int(
                                package_ref_sort_order if package_ref_sort_order is not None else result.get("sort_order"),
                                "atomic_activity.package_ref_sort_order",
                                default=0,
                            ),
                            is_active=True,
                            metadata_json=package_ref_metadata_json,
                        ),
                        db,
                    )
            elif operation == "update":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="atomic_activity update requires entity_id")
                result = await update_atomic_activity(entity_id, AtomicActivityUpdate(**payload), db)
            elif operation == "delete":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="atomic_activity delete requires entity_id")
                result = await delete_atomic_activity(entity_id, db)
            else:
                raise HTTPException(status_code=422, detail=f"Unsupported atomic_activity operation: {operation}")
            return _commit_result(index, entity_type, operation, result)

        if entity_type == "activity_package_atomic_ref":
            _resolve_network_editor_package_ref_refs(payload, draft_refs)
            if operation == "create":
                package_id = payload.pop("package_id", None)
                if not package_id:
                    raise HTTPException(status_code=422, detail="activity_package_atomic_ref create requires package_id")
                result = await create_activity_package_atomic_ref(
                    _coerce_network_editor_int(package_id, "activity_package_atomic_ref.package_id"),
                    ActivityPackageAtomicRefCreate(**payload),
                    db,
                )
            elif operation == "update":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="activity_package_atomic_ref update requires entity_id")
                result = await update_activity_package_atomic_ref(
                    entity_id,
                    ActivityPackageAtomicRefUpdate(**payload),
                    db,
                )
            elif operation == "delete":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="activity_package_atomic_ref delete requires entity_id")
                result = await delete_activity_package_atomic_ref(entity_id, db)
            else:
                raise HTTPException(status_code=422, detail=f"Unsupported activity_package_atomic_ref operation: {operation}")
            return _commit_result(index, entity_type, operation, result)

        if entity_type == "state_node_reference":
            _resolve_network_editor_state_reference_refs(payload, draft_refs)
            if operation == "create":
                state_node_id = payload.pop("state_node_id", None)
                if not state_node_id:
                    raise HTTPException(status_code=422, detail="state_node_reference create requires state_node_id")
                result = await create_state_node_reference(
                    _coerce_network_editor_int(state_node_id, "state_node_reference.state_node_id"),
                    StateNodeReferenceCreate(**payload),
                    db,
                )
            elif operation == "update":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="state_node_reference update requires entity_id")
                result = await update_state_node_reference(entity_id, StateNodeReferenceUpdate(**payload), db)
            elif operation == "delete":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="state_node_reference delete requires entity_id")
                result = await delete_state_node_reference(entity_id, db)
            else:
                raise HTTPException(status_code=422, detail=f"Unsupported state_node_reference operation: {operation}")
            return _commit_result(index, entity_type, operation, result)

        if entity_type == "state_package_fork":
            if operation != "create":
                raise HTTPException(status_code=422, detail=f"Unsupported state_package_fork operation: {operation}")
            _resolve_network_editor_state_package_fork_refs(payload, draft_refs)
            result = await _create_state_package_fork(machine_type_id, payload, db)
            return _commit_result(index, entity_type, operation, result)

        if entity_type == "op_rule":
            _resolve_network_editor_rule_refs(payload, draft_refs)
            if operation == "create":
                result = await create_op_rule(machine_type_id, OpRuleCreate(**payload), db)
                _store_network_editor_draft_ref(draft_refs, change.client_id, entity_type, result)
            elif operation == "update":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="op_rule update requires entity_id")
                result = await update_op_rule(entity_id, OpRuleUpdate(**payload), db)
            elif operation == "delete":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="op_rule delete requires entity_id")
                result = await delete_op_rule(entity_id, db)
            else:
                raise HTTPException(status_code=422, detail=f"Unsupported op_rule operation: {operation}")
            return _commit_result(index, entity_type, operation, result)

        if entity_type == "activity_state_binding":
            _resolve_network_editor_binding_refs(payload, draft_refs)
            if operation == "create":
                result = await create_activity_state_binding(ActivityStateBindingCreate(**payload), db)
            elif operation == "update":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="activity_state_binding update requires entity_id")
                result = await update_activity_state_binding(entity_id, ActivityStateBindingUpdate(**payload), db)
            elif operation == "delete":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="activity_state_binding delete requires entity_id")
                result = await delete_activity_state_binding(entity_id, db)
            elif operation == "refresh_coverage":
                if not entity_id:
                    raise HTTPException(status_code=422, detail="activity_state_binding refresh_coverage requires entity_id")
                result = await refresh_activity_state_binding_coverage(entity_id, db)
            else:
                raise HTTPException(status_code=422, detail=f"Unsupported activity_state_binding operation: {operation}")
            return _commit_result(index, entity_type, operation, result)
    except HTTPException as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "message": exc.detail,
                "change_index": index,
                "entity_type": entity_type,
                "operation": operation,
                "label": change.label,
            },
        ) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": f"Invalid network editor draft payload: {exc}",
                "change_index": index,
                "entity_type": entity_type,
                "operation": operation,
                "label": change.label,
            },
        ) from exc

    raise HTTPException(status_code=422, detail=f"Unsupported network editor entity_type: {entity_type}")


@router.post(
    "/machine-types/{machine_type_id}/network-editor/commit",
    response_model=NetworkEditorCommitResponse,
)
async def commit_network_editor_draft(
    machine_type_id: int,
    payload: NetworkEditorCommitRequest,
    db: AsyncSession = Depends(get_db_session),
):
    await _get_machine_type_or_404(machine_type_id, db)
    if payload.base_revision:
        current_revision = await get_network_editor_revision(db, machine_type_id)
        if current_revision != payload.base_revision:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Network editor data changed after this edit session started",
                    "base_revision": payload.base_revision,
                    "current_revision": current_revision,
                },
            )
    results = []
    draft_refs: dict[str, dict[str, Any]] = {}
    for index, change in enumerate(payload.changes):
        results.append(await _apply_network_editor_commit_change(machine_type_id, index, change, db, draft_refs))

    validation = None
    if payload.validate_after_apply:
        validation = await validate_network_editor_model(db, machine_type_id, payload.validation_payload)
        modeling_issues = validation.get("modeling_issues") or []
        solver_ready_issues = validation.get("solver_ready_issues") or []
        commit_blocking_issues = [
            issue for issue in modeling_issues
            if issue.get("severity") == "error"
        ]
        review_issues = [
            issue for issue in [*modeling_issues, *solver_ready_issues]
            if issue.get("severity") in {"warning", "error"}
            and issue not in commit_blocking_issues
        ]
        if commit_blocking_issues or (review_issues and not payload.allow_warnings):
            await db.rollback()
            raise HTTPException(
                status_code=422,
                detail={
                    "message": "Network editor validation requires review before unified submit",
                    "error_count": len(commit_blocking_issues),
                    "warning_count": len(review_issues),
                    "solver_ready_error_count": sum(
                        1 for issue in solver_ready_issues
                        if issue.get("severity") == "error"
                    ),
                    "validation": validation,
                },
            )

    return {
        "machine_type_id": machine_type_id,
        "applied_change_count": len(results),
        "results": results,
        "validation": validation,
        "revision": await get_network_editor_revision(db, machine_type_id),
    }


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


@router.get("/features/blockage-reasons", response_model=list[str])
async def list_blockage_reasons(db: AsyncSession = Depends(get_db_session)):
    """Return configured Strategy B reasons without exposing a feature key to the UI."""
    feature = await db.get(FeatureDefinition, "blockage_reason")
    if feature is None or feature.allowed_values is None:
        return []
    values = feature.allowed_values
    if isinstance(values, dict):
        values = next(
            (
                values[key]
                for key in ("values", "options", "allowed_values", "items")
                if isinstance(values.get(key), list)
            ),
            [],
        )
    if not isinstance(values, list):
        return []
    return [
        str(value)
        for value in values
        if value is not None and str(value).strip().lower() != "none"
    ]


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
