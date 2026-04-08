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

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import Select, delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    CandidatePlanStep,
    Machine,
    MachineState,
    MachineStateFeature,
    MachineType,
    OpRule,
    OpRuleEffect,
    OpRulePrecond,
    OpRuleResourceReq,
    Resource,
    SolveRequest,
    StateFeatureDef,
)
from app.db.schemas import (
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
    OpRuleCreate,
    OpRuleDetailResponse,
    OpRuleUpdate,
    ResourceCreate,
    ResourceResponse,
    ResourceUpdate,
    StateFeatureDefCreate,
    StateFeatureDefResponse,
    StateFeatureDefUpdate,
)
from app.db.session import get_db_session

router = APIRouter(tags=["master-data"])


def _extract_allowed_values(payload: Optional[dict[str, Any]]) -> Optional[set[str]]:
    """Accept a few frontend-friendly shapes for enum values."""
    if not payload:
        return None

    candidates = None
    for key in ("values", "options", "allowed_values", "items"):
        if isinstance(payload.get(key), list):
            candidates = payload[key]
            break

    if candidates is None and all(isinstance(k, str) for k in payload.keys()):
        # Fallback: {"cold": "...", "hot": "..."} -> validate against keys
        candidates = list(payload.keys())

    if not candidates:
        return None

    return {str(item) for item in candidates}


def _normalize_allowed_values(payload: Any) -> Optional[dict[str, Any]]:
    """Return frontend-friendly allowed_values shape regardless of stored format."""
    if payload is None:
        return None
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, list):
        return {"values": [str(item) for item in payload]}
    return {"values": [str(payload)]}


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
        "code": rule.code,
        "name": rule.name,
        "duration_min": rule.duration_min,
        "description": rule.description,
        "is_active": rule.is_active,
        "created_at": rule.created_at,
        "preconditions": [
            {
                "id": item.id,
                "feature_key": item.feature_key,
                "operator": item.operator,
                "feature_value": item.feature_value,
            }
            for item in rule.preconditions
        ],
        "effects": [
            {
                "id": item.id,
                "feature_key": item.feature_key,
                "new_value": item.new_value,
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

    obj.feature_key = payload.feature_key
    obj.feature_name = payload.feature_name
    obj.value_type = payload.value_type
    obj.allowed_values = payload.allowed_values
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
    await _get_machine_type_or_404(machine_type_id, db)
    await _ensure_unique(db, OpRule, "code", payload.code)
    if not payload.effects:
        raise HTTPException(status_code=422, detail="An operation rule must have at least one effect")
    await _validate_rule_features(db, machine_type_id, payload.preconditions, payload.effects)

    rule = OpRule(
        machine_type_id=machine_type_id,
        code=payload.code,
        name=payload.name,
        duration_min=payload.duration_min,
        description=payload.description,
        is_active=payload.is_active,
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
    await _ensure_unique(db, OpRule, "code", payload.code, exclude_id=rule_id)
    if not payload.effects:
        raise HTTPException(status_code=422, detail="An operation rule must have at least one effect")
    await _validate_rule_features(db, payload.machine_type_id, payload.preconditions, payload.effects)

    rule.machine_type_id = payload.machine_type_id
    rule.code = payload.code
    rule.name = payload.name
    rule.duration_min = payload.duration_min
    rule.description = payload.description
    rule.is_active = payload.is_active
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
    resource_type: Optional[str] = Query(default=None),
    db: AsyncSession = Depends(get_db_session),
):
    query: Select = select(Resource).order_by(Resource.id)
    if resource_type:
        query = query.where(Resource.resource_type == resource_type)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/resources", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(payload: ResourceCreate, db: AsyncSession = Depends(get_db_session)):
    await _ensure_unique(db, Resource, "code", payload.code)
    obj = Resource(
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
    await _ensure_unique(db, Resource, "code", payload.code, exclude_id=resource_id)
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
