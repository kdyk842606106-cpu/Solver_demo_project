"""
Pydantic Schemas for request/response validation.

This module defines data transfer objects (DTOs) for API serialization
and deserialization, following the contracts defined in docs/protocols/.
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================
# Base Configuration
# ============================================================


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ============================================================
# 机台与状态相关 Schemas
# ============================================================


class MachineTypeCreate(BaseModel):
    """Schema for creating a machine type."""

    code: str = Field(..., min_length=1, max_length=64, description="Machine type code")
    name: str = Field(..., min_length=1, max_length=128, description="Machine type name")
    description: Optional[str] = Field(None, description="Machine type description")


class MachineTypeUpdate(BaseModel):
    """Schema for updating a machine type."""

    code: str = Field(..., min_length=1, max_length=64, description="Machine type code")
    name: str = Field(..., min_length=1, max_length=128, description="Machine type name")
    description: Optional[str] = Field(None, description="Machine type description")


class MachineTypeResponse(BaseSchema):
    """Schema for machine type response."""

    id: int
    code: str
    name: str
    description: Optional[str] = None
    created_at: datetime


class MachineCreate(BaseModel):
    """Schema for creating a machine."""

    machine_type_id: int = Field(..., gt=0, description="Machine type ID")
    code: str = Field(..., min_length=1, max_length=64, description="Machine code")
    name: str = Field(..., min_length=1, max_length=128, description="Machine name")
    location: Optional[str] = Field(None, max_length=128, description="Machine location")


class MachineUpdate(BaseModel):
    """Schema for updating a machine."""

    machine_type_id: int = Field(..., gt=0, description="Machine type ID")
    code: str = Field(..., min_length=1, max_length=64, description="Machine code")
    name: str = Field(..., min_length=1, max_length=128, description="Machine name")
    location: Optional[str] = Field(None, max_length=128, description="Machine location")


class MachineResponse(BaseSchema):
    """Schema for machine response."""

    id: int
    machine_type_id: int
    code: str
    name: str
    location: Optional[str] = None
    created_at: datetime


class StateFeatureDefCreate(BaseModel):
    """Schema for creating a state feature definition."""

    machine_type_id: int = Field(..., gt=0, description="Machine type ID")
    feature_key: str = Field(..., min_length=1, max_length=64, description="Feature key")
    feature_name: Optional[str] = Field(None, max_length=128, description="Feature name")
    value_type: str = Field(..., description="Value type: string, number, boolean, or enum")
    allowed_values: Optional[list[Any]] = Field(None, description="Allowed values for enum type")


class StateFeatureDefUpdate(BaseModel):
    """Schema for updating a state feature definition."""

    feature_key: str = Field(..., min_length=1, max_length=64, description="Feature key")
    feature_name: Optional[str] = Field(None, max_length=128, description="Feature name")
    value_type: str = Field(..., description="Value type: string, number, boolean, or enum")
    allowed_values: Optional[list[Any]] = Field(None, description="Allowed values for enum type")


class StateFeatureDefResponse(BaseSchema):
    """Schema for state feature definition response."""

    id: int
    machine_type_id: int
    feature_key: str
    feature_name: Optional[str] = None
    value_type: str
    allowed_values: Optional[list[Any]] = None


class MachineStateFeatureCreate(BaseModel):
    """Schema for creating a machine state feature."""

    feature_key: str = Field(..., min_length=1, max_length=64, description="Feature key")
    feature_value: str = Field(..., min_length=1, max_length=256, description="Feature value")


class MachineStateFeatureResponse(BaseSchema):
    """Schema for machine state feature response."""

    id: int
    feature_key: str
    feature_value: str


class MachineStateCreate(BaseModel):
    """Schema for creating a machine state."""

    machine_id: int = Field(..., gt=0, description="Machine ID")
    state_type: str = Field(..., description="State type: current, target, or snapshot")
    label: Optional[str] = Field(None, max_length=128, description="State label")
    features: dict[str, str] = Field(default_factory=dict, description="State features as key-value pairs")


class MachineStateUpdate(BaseModel):
    """Schema for updating a machine state."""

    state_type: str = Field(..., description="State type: current, target, or snapshot")
    label: Optional[str] = Field(None, max_length=128, description="State label")
    features: dict[str, str] = Field(default_factory=dict, description="State features as key-value pairs")


class MachineStateResponse(BaseSchema):
    """Schema for machine state response."""

    id: int
    machine_id: int
    state_type: str
    label: Optional[str] = None
    created_at: datetime
    features: dict[str, str] = Field(default_factory=dict, description="State features as key-value pairs")


# ============================================================
# 工序规则相关 Schemas
# ============================================================


class OpRulePrecondCreate(BaseModel):
    """Schema for creating an operation rule precondition."""

    feature_key: str = Field(..., min_length=1, max_length=64, description="Feature key")
    operator: str = Field(default="eq", description="Comparison operator: eq, neq, gt, gte, lt, lte, in")
    feature_value: str = Field(..., min_length=1, max_length=256, description="Feature value")
    value_list: Optional[list[Any]] = Field(None, description="Value list for 'in' operator")


class OpRulePrecondResponse(BaseSchema):
    """Schema for operation rule precondition response."""

    id: int
    feature_key: str
    operator: str
    feature_value: str
    value_list: Optional[list[Any]] = None


class OpRuleEffectCreate(BaseModel):
    """Schema for creating an operation rule effect."""

    feature_key: str = Field(..., min_length=1, max_length=64, description="Feature key")
    new_value: str = Field(..., min_length=1, max_length=256, description="New value after effect")
    effect_type: str = Field(default="set", description="Effect type: set, increment, decrement")
    delta_value: Optional[float] = Field(None, description="Delta value for increment/decrement")


class OpRuleEffectResponse(BaseSchema):
    """Schema for operation rule effect response."""

    id: int
    feature_key: str
    new_value: str
    effect_type: str
    delta_value: Optional[float] = None


class OpRuleResourceReqCreate(BaseModel):
    """Schema for creating an operation rule resource requirement."""

    resource_type: str = Field(..., min_length=1, max_length=64, description="Resource type")
    quantity: int = Field(default=1, ge=1, description="Required quantity")
    is_required: bool = Field(default=True, description="Whether the resource is required")


class OpRuleResourceReqResponse(BaseSchema):
    """Schema for operation rule resource requirement response."""

    id: int
    resource_type: str
    quantity: int
    is_required: bool


class OpRuleCreate(BaseModel):
    """Schema for creating an operation rule."""

    machine_type_id: int = Field(..., gt=0, description="Machine type ID")
    code: str = Field(..., min_length=1, max_length=64, description="Operation code")
    name: str = Field(..., min_length=1, max_length=128, description="Operation name")
    duration_min: int = Field(default=30, ge=1, description="Duration in minutes")
    description: Optional[str] = Field(None, description="Operation description")
    is_active: bool = Field(default=True, description="Whether the operation is active")
    is_repair: bool = Field(default=False, description="Whether this is a repair operation")
    valid_from: Optional[datetime] = Field(None, description="Valid start timestamp")
    valid_to: Optional[datetime] = Field(None, description="Valid end timestamp")
    preconditions: list[OpRulePrecondCreate] = Field(default_factory=list, description="Preconditions")
    effects: list[OpRuleEffectCreate] = Field(default_factory=list, description="Effects")
    resource_reqs: list[OpRuleResourceReqCreate] = Field(default_factory=list, description="Resource requirements")


class OpRuleUpdate(BaseModel):
    """Schema for updating an operation rule."""

    machine_type_id: int = Field(..., gt=0, description="Machine type ID")
    code: str = Field(..., min_length=1, max_length=64, description="Operation code")
    name: str = Field(..., min_length=1, max_length=128, description="Operation name")
    duration_min: int = Field(default=30, ge=1, description="Duration in minutes")
    description: Optional[str] = Field(None, description="Operation description")
    is_active: bool = Field(default=True, description="Whether the operation is active")
    is_repair: bool = Field(default=False, description="Whether this is a repair operation")
    valid_from: Optional[datetime] = Field(None, description="Valid start timestamp")
    valid_to: Optional[datetime] = Field(None, description="Valid end timestamp")
    preconditions: list[OpRulePrecondCreate] = Field(default_factory=list, description="Preconditions")
    effects: list[OpRuleEffectCreate] = Field(default_factory=list, description="Effects")
    resource_reqs: list[OpRuleResourceReqCreate] = Field(default_factory=list, description="Resource requirements")


class OpRuleResponse(BaseSchema):
    """Schema for operation rule response."""

    id: int
    machine_type_id: int
    code: str
    name: str
    duration_min: int
    description: Optional[str] = None
    is_active: bool
    is_repair: bool
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    created_at: datetime
    preconditions: list[OpRulePrecondResponse] = Field(default_factory=list)
    effects: list[OpRuleEffectResponse] = Field(default_factory=list)
    resource_reqs: list[OpRuleResourceReqResponse] = Field(default_factory=list)


# ============================================================
# 资源相关 Schemas
# ============================================================


class ResourceCreate(BaseModel):
    """Schema for creating a resource."""

    code: str = Field(..., min_length=1, max_length=64, description="Resource code")
    name: str = Field(..., min_length=1, max_length=128, description="Resource name")
    resource_type: str = Field(..., min_length=1, max_length=64, description="Resource type")
    capacity: int = Field(default=1, ge=1, description="Resource capacity")
    is_available: bool = Field(default=True, description="Whether the resource is available")
    meta: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class ResourceUpdate(BaseModel):
    """Schema for updating a resource."""

    code: str = Field(..., min_length=1, max_length=64, description="Resource code")
    name: str = Field(..., min_length=1, max_length=128, description="Resource name")
    resource_type: str = Field(..., min_length=1, max_length=64, description="Resource type")
    capacity: int = Field(default=1, ge=1, description="Resource capacity")
    is_available: bool = Field(default=True, description="Whether the resource is available")
    meta: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class ResourceResponse(BaseSchema):
    """Schema for resource response."""

    id: int
    code: str
    name: str
    resource_type: str
    capacity: int
    is_available: bool
    meta: Optional[dict[str, Any]] = None


# ============================================================
# 特征定义 Schemas
# ============================================================


class FeatureDefinitionCreate(BaseModel):
    """Schema for creating a feature definition."""

    feature_key: str = Field(..., min_length=1, max_length=64, description="Feature key")
    value_type: str = Field(..., description="Value type: string, number, boolean, enum")
    allowed_values: Optional[list[Any]] = Field(None, description="Allowed values for enum type")
    unit: Optional[str] = Field(None, max_length=32, description="Unit of measurement")
    description: Optional[str] = Field(None, description="Feature description")


class FeatureDefinitionResponse(BaseSchema):
    """Schema for feature definition response."""

    feature_key: str
    value_type: str
    allowed_values: Optional[list[Any]] = None
    unit: Optional[str] = None
    description: Optional[str] = None


# ============================================================
# 求解请求相关 Schemas
# ============================================================


class SolveRequestCreate(BaseModel):
    """Schema for creating a solve request."""

    machine_id: int = Field(..., gt=0, description="Machine ID")
    current_state_id: int = Field(..., gt=0, description="Current state ID")
    target_state_id: int = Field(..., gt=0, description="Target state ID")
    objective: str = Field(default="minimize_makespan", description="Optimization objective")
    objectives: Optional[list[dict[str, Any]]] = Field(None, description="Objectives array")
    constraints: Optional[dict[str, Any]] = Field(None, description="Constraints")
    parent_plan_id: Optional[int] = Field(None, description="Parent plan ID for replanning")
    overrides: Optional[dict[str, Any]] = Field(None, description="Override rules")
    blockage_constraints: Optional[dict[str, Any]] = Field(
        None,
        description="Blockage constraints: {strategy: A|B|AB, blocked_step_id, strategy_a: {not_before_offset}, strategy_b: {blockage_reason}, ...}",
    )


class SolveRequestResponse(BaseSchema):
    """Schema for solve request response."""

    id: int
    machine_id: int
    current_state_id: int
    target_state_id: int
    objective: str
    objectives: Optional[list[dict[str, Any]]] = None
    constraints: Optional[dict[str, Any]] = None
    parent_plan_id: Optional[int] = None
    status: str
    overrides: Optional[dict[str, Any]] = None
    created_at: datetime
    solved_at: Optional[datetime] = None


# ============================================================
# 结果相关 Schemas
# ============================================================


class ScheduleTaskItem(BaseSchema):
    """Schema for a single scheduled task."""

    step_order: int = Field(..., description="Step order in the plan")
    op_rule_id: int = Field(..., description="Operation rule ID")
    op_rule_code: str = Field(..., description="Operation code")
    start_min: int = Field(..., ge=0, description="Start time in minutes")
    end_min: int = Field(..., ge=0, description="End time in minutes")
    duration_min: int = Field(..., ge=1, description="Duration in minutes")
    predecessors: list[int] = Field(default_factory=list, description="Predecessor step orders")
    resources: list[dict[str, Any]] = Field(default_factory=list, description="Assigned resources")
    not_before: Optional[int] = Field(None, description="Not before constraint in minutes")
    step_role: str = Field(default="normal", description="Step role: normal/repair/pulled_forward/delayed")


class CandidatePlanStepResponse(BaseSchema):
    """Schema for candidate plan step response."""

    id: int
    step_order: int
    op_rule_id: int
    op_rule_code: Optional[str] = None
    predecessor_ids: list[int] = Field(default_factory=list)
    not_before: Optional[int] = None
    step_role: str = "normal"


class CandidatePlanResponse(BaseSchema):
    """Schema for candidate plan response."""

    id: int
    solve_request_id: int
    total_steps: Optional[int] = None
    search_method: str
    version: int = 1
    parent_plan_id: Optional[int] = None
    replan_reason: Optional[str] = None
    status: str = "draft"
    created_at: datetime
    steps: list[CandidatePlanStepResponse] = Field(default_factory=list)


class ScheduleResultResponse(BaseSchema):
    """Schema for schedule result response."""

    id: int
    solve_request_id: int
    candidate_plan_id: int
    makespan: Optional[int] = None
    solver_status: Optional[str] = None
    tasks: list[ScheduleTaskItem] = Field(default_factory=list)
    created_at: datetime


# ============================================================
# API 响应 Schemas
# ============================================================


class SolveResponse(BaseSchema):
    """Schema for the complete solve API response."""

    solve_request_id: int
    status: str
    candidate_plan_id: Optional[int] = None
    schedule: Optional[ScheduleResultResponse] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class PlanVersionItem(BaseSchema):
    """Single entry in a plan version chain."""

    id: int
    version: int
    replan_reason: Optional[str] = None
    parent_plan_id: Optional[int] = None
    status: str
    total_steps: Optional[int] = None
    created_at: datetime


class PlanDiffStep(BaseModel):
    """One step entry in a plan-vs-plan diff."""

    op_code: str
    base_start: Optional[int] = None
    base_end: Optional[int] = None
    new_start: Optional[int] = None
    new_end: Optional[int] = None
    step_role: str = "normal"
    not_before: Optional[int] = None


class PlanDiffResponse(BaseModel):
    """Response for GET /plans/{id}/diff/{other_id}."""

    base_plan_id: int
    new_plan_id: int
    base_makespan: Optional[int] = None
    new_makespan: Optional[int] = None
    steps: list[PlanDiffStep] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Schema for error responses."""

    error_code: str
    error_message: str
    details: Optional[dict[str, Any]] = None


class MachineTypeDetailResponse(BaseSchema):
    """Aggregated machine type response for frontend data management."""

    id: int
    code: str
    name: str
    description: Optional[str] = None
    created_at: datetime
    feature_defs: list[StateFeatureDefResponse] = Field(default_factory=list)


class MachineDetailResponse(BaseSchema):
    """Aggregated machine response for frontend data management."""

    id: int
    machine_type_id: int
    machine_type_code: Optional[str] = None
    code: str
    name: str
    location: Optional[str] = None
    created_at: datetime


class MachineStateDetailResponse(BaseSchema):
    """State detail response with flattened features."""

    state_id: int
    machine_id: int
    state_type: str
    label: Optional[str] = None
    created_at: datetime
    features: dict[str, str] = Field(default_factory=dict)


class OpRuleDetailResponse(BaseSchema):
    """Detailed op rule response for frontend CRUD."""

    id: int
    machine_type_id: int
    code: str
    name: str
    duration_min: int
    description: Optional[str] = None
    is_active: bool
    is_repair: bool = False
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    created_at: datetime
    preconditions: list[OpRulePrecondResponse] = Field(default_factory=list)
    effects: list[OpRuleEffectResponse] = Field(default_factory=list)
    resource_reqs: list[OpRuleResourceReqResponse] = Field(default_factory=list)


# ============================================================
# 阻塞事件 Schemas
# ============================================================


# ============================================================
# State Query Response Schemas
# ============================================================


class StateListItem(BaseSchema):
    """A single state entry in the machine states list."""

    state_id: int
    state_type: str
    label: Optional[str] = None
    features: dict[str, str] = Field(default_factory=dict)


class MachineStatesListResponse(BaseSchema):
    """Response for GET /machines/{id}/states."""

    machine_id: int
    machine_code: str
    states: list[StateListItem] = Field(default_factory=list)


class CurrentStateDetail(BaseSchema):
    """Current state detail inside MachineCurrentStateResponse."""

    state_id: int
    label: Optional[str] = None
    features: dict[str, str] = Field(default_factory=dict)


class MachineCurrentStateResponse(BaseSchema):
    """Response for GET /machines/{id}/state."""

    machine_id: int
    machine_code: str
    current_state: CurrentStateDetail


class ScheduleSummary(BaseSchema):
    """Inline schedule summary for solve request response."""

    makespan: Optional[int] = None
    solver_status: Optional[str] = None
    tasks: list[dict[str, Any]] = Field(default_factory=list)


class SolveRequestDetailResponse(BaseSchema):
    """Response for GET /solve-requests/{id}."""

    id: int
    machine_id: int
    status: str
    objective: str
    created_at: Optional[str] = None
    solved_at: Optional[str] = None
    candidate_plan_id: Optional[int] = None
    schedule: Optional[ScheduleSummary] = None


# ============================================================
# 阻塞事件 Schemas
# ============================================================


class BlockageEventCreate(BaseModel):
    """Schema for creating a blockage event."""

    plan_id: int = Field(..., gt=0, description="Plan ID")
    blocked_step_id: int = Field(..., gt=0, description="Blocked step ID")
    strategy: str = Field(..., description="Strategy: A, B, or AB")
    not_before_offset: Optional[int] = Field(None, ge=0, description="Not before offset in minutes")
    blockage_reason: Optional[str] = Field(None, max_length=64, description="Blockage reason")
    note: Optional[str] = Field(None, description="Note")
    created_by: Optional[str] = Field(None, max_length=64, description="Created by")


class BlockageEventResponse(BaseSchema):
    """Schema for blockage event response."""

    id: int
    plan_id: int
    blocked_step_id: int
    strategy: str
    not_before_offset: Optional[int] = None
    blockage_reason: Optional[str] = None
    note: Optional[str] = None
    created_at: datetime
    created_by: Optional[str] = None



