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
    effect_type: str = Field(default="set", description="Effect type: set, increment, decrement, sub, reset")
    delta_value: Optional[float] = Field(None, description="Delta value for increment/decrement/sub")


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
    activity_node_id: Optional[int] = Field(None, gt=0, description="Optional level-3 activity node ID")
    atomic_activity_id: Optional[int] = Field(None, gt=0, description="Optional atomic activity ID")
    code: Optional[str] = Field(None, max_length=64, description="Operation code")
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
    activity_node_id: Optional[int] = Field(None, gt=0, description="Optional level-3 activity node ID")
    atomic_activity_id: Optional[int] = Field(None, gt=0, description="Optional atomic activity ID")
    code: Optional[str] = Field(None, max_length=64, description="Operation code")
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
    activity_node_id: Optional[int] = None
    atomic_activity_id: Optional[int] = None
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

    machine_id: int = Field(..., gt=0, description="Machine ID")
    code: str = Field(..., min_length=1, max_length=64, description="Resource code")
    name: str = Field(..., min_length=1, max_length=128, description="Resource name")
    resource_type: str = Field(..., min_length=1, max_length=64, description="Resource type")
    capacity: int = Field(default=1, ge=1, description="Resource capacity")
    is_available: bool = Field(default=True, description="Whether the resource is available")
    meta: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class ResourceUpdate(BaseModel):
    """Schema for updating a resource."""

    machine_id: int = Field(..., gt=0, description="Machine ID")
    code: str = Field(..., min_length=1, max_length=64, description="Resource code")
    name: str = Field(..., min_length=1, max_length=128, description="Resource name")
    resource_type: str = Field(..., min_length=1, max_length=64, description="Resource type")
    capacity: int = Field(default=1, ge=1, description="Resource capacity")
    is_available: bool = Field(default=True, description="Whether the resource is available")
    meta: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class ResourceResponse(BaseSchema):
    """Schema for resource response."""

    id: int
    machine_id: int
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
# 分层活动 / 分层状态 Schemas
# ============================================================


class ActivityNodeCreate(BaseModel):
    """Schema for creating a layered activity node."""

    machine_type_id: int = Field(..., gt=0, description="Machine type ID")
    parent_id: Optional[int] = Field(None, gt=0, description="Parent activity node ID")
    level: int = Field(..., ge=1, le=3, description="Hierarchy level: 1, 2, or legacy 3")
    code: Optional[str] = Field(None, max_length=64, description="Activity node code")
    name: str = Field(..., min_length=1, max_length=128, description="Activity node name")
    description: Optional[str] = Field(None, description="Activity node description")
    activity_category: str = Field(default="normal", max_length=32, description="normal/repair/maintenance")
    sort_order: int = Field(default=0, description="Display order under the same parent")
    is_active: bool = Field(default=True, description="Whether this node is active")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class ActivityNodeUpdate(BaseModel):
    """Schema for updating a layered activity node."""

    parent_id: Optional[int] = Field(None, gt=0, description="Parent activity node ID")
    level: int = Field(..., ge=1, le=3, description="Hierarchy level: 1, 2, or legacy 3")
    code: Optional[str] = Field(None, max_length=64, description="Activity node code")
    name: str = Field(..., min_length=1, max_length=128, description="Activity node name")
    description: Optional[str] = Field(None, description="Activity node description")
    activity_category: str = Field(default="normal", max_length=32, description="normal/repair/maintenance")
    sort_order: int = Field(default=0, description="Display order under the same parent")
    is_active: bool = Field(default=True, description="Whether this node is active")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class ActivityNodeResponse(BaseSchema):
    """Schema for a layered activity node response."""

    id: int
    machine_type_id: int
    parent_id: Optional[int] = None
    level: int
    code: str
    name: str
    description: Optional[str] = None
    activity_category: str = "normal"
    sort_order: int = 0
    is_active: bool
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime


class AtomicActivityCreate(BaseModel):
    """Schema for creating a reusable atomic activity."""

    machine_type_id: int = Field(..., gt=0, description="Machine type ID")
    code: Optional[str] = Field(None, max_length=64, description="Atomic activity code")
    name: str = Field(..., min_length=1, max_length=128, description="Atomic activity name")
    description: Optional[str] = Field(None, description="Atomic activity description")
    activity_category: str = Field(default="normal", max_length=32, description="normal/repair/maintenance")
    sort_order: int = Field(default=0, description="Display order")
    is_active: bool = Field(default=True, description="Whether this atomic activity is active")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class AtomicActivityUpdate(BaseModel):
    """Schema for updating a reusable atomic activity."""

    code: Optional[str] = Field(None, max_length=64, description="Atomic activity code")
    name: str = Field(..., min_length=1, max_length=128, description="Atomic activity name")
    description: Optional[str] = Field(None, description="Atomic activity description")
    activity_category: str = Field(default="normal", max_length=32, description="normal/repair/maintenance")
    sort_order: int = Field(default=0, description="Display order")
    is_active: bool = Field(default=True, description="Whether this atomic activity is active")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class AtomicActivityResponse(BaseSchema):
    """Schema for a reusable atomic activity response."""

    id: int
    machine_type_id: int
    code: str
    name: str
    description: Optional[str] = None
    activity_category: str = "normal"
    sort_order: int = 0
    is_active: bool
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime


class ActivityPackageAtomicRefCreate(BaseModel):
    """Schema for attaching an atomic activity to a level-2 activity package."""

    atomic_activity_id: int = Field(..., gt=0, description="Atomic activity ID")
    sort_order: int = Field(default=0, description="Display order inside package")
    is_active: bool = Field(default=True, description="Whether this package reference is active")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class ActivityPackageAtomicRefUpdate(BaseModel):
    """Schema for updating an activity-package atomic activity reference."""

    atomic_activity_id: Optional[int] = Field(None, gt=0, description="Atomic activity ID")
    sort_order: int = Field(default=0, description="Display order inside package")
    is_active: bool = Field(default=True, description="Whether this package reference is active")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class ActivityPackageAtomicRefResponse(BaseSchema):
    """Schema for an activity-package atomic activity reference."""

    id: int
    activity_node_id: int
    atomic_activity_id: int
    atomic_activity_code: Optional[str] = None
    atomic_activity_name: Optional[str] = None
    activity_category: Optional[str] = None
    sort_order: int = 0
    is_active: bool
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime


class StateNodeCreate(BaseModel):
    """Schema for creating a layered state node."""

    machine_type_id: int = Field(..., gt=0, description="Machine type ID")
    parent_id: Optional[int] = Field(None, gt=0, description="Parent state node ID")
    level: int = Field(..., ge=1, description="Hierarchy level")
    code: Optional[str] = Field(None, max_length=64, description="State node code")
    name: str = Field(..., min_length=1, max_length=128, description="State node name")
    feature_key: Optional[str] = Field(None, max_length=64, description="Leaf feature key")
    operator: str = Field(default="eq", max_length=16, description="Leaf completion operator")
    target_value: Optional[str] = Field(None, max_length=256, description="Leaf target value")
    state_kind: str = Field(default="aggregate", max_length=32, description="aggregate/atomic/external/manual")
    sort_order: int = Field(default=0, description="Display order under the same parent")
    is_active: bool = Field(default=True, description="Whether this node is active")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class StateNodeUpdate(BaseModel):
    """Schema for updating a layered state node."""

    parent_id: Optional[int] = Field(None, gt=0, description="Parent state node ID")
    level: int = Field(..., ge=1, description="Hierarchy level")
    code: Optional[str] = Field(None, max_length=64, description="State node code")
    name: str = Field(..., min_length=1, max_length=128, description="State node name")
    feature_key: Optional[str] = Field(None, max_length=64, description="Leaf feature key")
    operator: str = Field(default="eq", max_length=16, description="Leaf completion operator")
    target_value: Optional[str] = Field(None, max_length=256, description="Leaf target value")
    state_kind: str = Field(default="aggregate", max_length=32, description="aggregate/atomic/external/manual")
    sort_order: int = Field(default=0, description="Display order under the same parent")
    is_active: bool = Field(default=True, description="Whether this node is active")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class StateNodeResponse(BaseSchema):
    """Schema for a layered state node response."""

    id: int
    machine_type_id: int
    parent_id: Optional[int] = None
    level: int
    code: str
    name: str
    feature_key: Optional[str] = None
    operator: str = "eq"
    target_value: Optional[str] = None
    state_kind: str = "aggregate"
    sort_order: int = 0
    is_active: bool
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime


class StateNodeReferenceCreate(BaseModel):
    """Schema for adding an additional display parent to a state node."""

    parent_state_node_id: int = Field(..., gt=0, description="Additional parent state node ID")
    sort_order: int = Field(default=0, description="Display order under the reference parent")
    is_active: bool = Field(default=True, description="Whether this reference is active")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class StateNodeReferenceUpdate(BaseModel):
    """Schema for updating a state reference display instance."""

    sort_order: int = Field(default=0, description="Display order under the reference parent")
    is_active: bool = Field(default=True, description="Whether this reference is active")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class StateNodeReferenceResponse(BaseSchema):
    """Schema for a state node reference response."""

    id: int
    state_node_id: int
    state_node_code: Optional[str] = None
    state_node_name: Optional[str] = None
    parent_state_node_id: int
    parent_state_node_code: Optional[str] = None
    parent_state_node_name: Optional[str] = None
    sort_order: int = 0
    is_active: bool
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime


class ActivityStateBindingCreate(BaseModel):
    """Schema for creating a network-editor state/activity binding."""

    machine_type_id: int = Field(..., gt=0, description="Machine type ID")
    activity_node_id: Optional[int] = Field(None, gt=0, description="Virtual activity node ID")
    atomic_activity_id: Optional[int] = Field(None, gt=0, description="Executable atomic activity ID")
    op_rule_id: Optional[int] = Field(None, gt=0, description="Linked executable rule ID")
    state_node_id: int = Field(..., gt=0, description="Bound state node ID")
    binding_role: str = Field(..., description="input/output/context_input/declared_output")
    covered_leaf_state_ids: Optional[list[int]] = Field(None, description="Snapshot of covered leaf state IDs")
    is_inherited: bool = Field(default=False, description="Whether this is an inherited projection")
    is_active: bool = Field(default=True, description="Whether this binding is active")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class ActivityStateBindingUpdate(BaseModel):
    """Schema for updating a network-editor state/activity binding."""

    machine_type_id: int = Field(..., gt=0, description="Machine type ID")
    activity_node_id: Optional[int] = Field(None, gt=0, description="Virtual activity node ID")
    atomic_activity_id: Optional[int] = Field(None, gt=0, description="Executable atomic activity ID")
    op_rule_id: Optional[int] = Field(None, gt=0, description="Linked executable rule ID")
    state_node_id: int = Field(..., gt=0, description="Bound state node ID")
    binding_role: str = Field(..., description="input/output/context_input/declared_output")
    covered_leaf_state_ids: Optional[list[int]] = Field(None, description="Snapshot of covered leaf state IDs")
    is_inherited: bool = Field(default=False, description="Whether this is an inherited projection")
    is_active: bool = Field(default=True, description="Whether this binding is active")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Additional metadata")


class ActivityStateBindingResponse(BaseSchema):
    """Schema for a network-editor state/activity binding response."""

    id: int
    machine_type_id: int
    activity_node_id: Optional[int] = None
    activity_node_code: Optional[str] = None
    activity_node_name: Optional[str] = None
    atomic_activity_id: Optional[int] = None
    atomic_activity_code: Optional[str] = None
    atomic_activity_name: Optional[str] = None
    op_rule_id: Optional[int] = None
    op_rule_code: Optional[str] = None
    op_rule_name: Optional[str] = None
    state_node_id: int
    state_node_code: Optional[str] = None
    state_node_name: Optional[str] = None
    binding_role: str
    binding_type: str
    coverage_policy: str = "snapshot"
    covered_leaf_state_ids: list[int] = Field(default_factory=list)
    coverage_status: str
    is_inherited: bool
    is_active: bool
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime


class ScopeGuardPrecondCreate(BaseModel):
    """Schema for creating a Scope Guard precondition."""

    state_node_id: int = Field(..., gt=0, description="Referenced state node ID")
    operator: str = Field(default="completed", max_length=16, description="completed/eq/gt/gte/lt/lte/in")
    expected_value: Optional[str] = Field(None, max_length=256, description="Expected value for non-completed operators")
    value_list: Optional[list[Any]] = Field(None, description="Value list for in operator")


class ScopeGuardPrecondResponse(BaseSchema):
    """Schema for a Scope Guard precondition response."""

    id: int
    state_node_id: int
    state_node_code: Optional[str] = None
    state_node_name: Optional[str] = None
    state_node_level: Optional[int] = None
    operator: str
    expected_value: Optional[str] = None
    value_list: Optional[list[Any]] = None


class ScopeGuardCreate(BaseModel):
    """Schema for creating a Scope Guard."""

    activity_node_id: int = Field(..., gt=0, description="Level-1 or level-2 activity node ID")
    name: str = Field(..., min_length=1, max_length=128, description="Scope Guard name")
    description: Optional[str] = Field(None, description="Scope Guard description")
    is_active: bool = Field(default=True, description="Whether this Scope Guard is active")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Additional metadata")
    preconditions: list[ScopeGuardPrecondCreate] = Field(default_factory=list, description="State preconditions")


class ScopeGuardUpdate(BaseModel):
    """Schema for updating a Scope Guard."""

    name: str = Field(..., min_length=1, max_length=128, description="Scope Guard name")
    description: Optional[str] = Field(None, description="Scope Guard description")
    is_active: bool = Field(default=True, description="Whether this Scope Guard is active")
    metadata_json: Optional[dict[str, Any]] = Field(None, description="Additional metadata")
    preconditions: list[ScopeGuardPrecondCreate] = Field(default_factory=list, description="State preconditions")


class ScopeGuardResponse(BaseSchema):
    """Schema for a Scope Guard response."""

    id: int
    activity_node_id: int
    name: str
    description: Optional[str] = None
    is_active: bool
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime
    preconditions: list[ScopeGuardPrecondResponse] = Field(default_factory=list)


class LayeredExpansionRequest(BaseModel):
    """Request for expanding layered targets and activity scopes."""

    target_state_node_ids: list[int] = Field(default_factory=list, description="Selected state node IDs")
    activity_scope_node_ids: list[int] = Field(
        default_factory=list,
        description="Selected activity node IDs; empty means all active atomic activities",
    )
    include_inactive: bool = Field(default=False, description="Include inactive nodes and guards")


class LayeredPathItem(BaseModel):
    """One node in an activity/state path."""

    id: int
    code: str
    name: str
    level: int


class LayeredGoalFact(BaseModel):
    """Expanded leaf goal fact from a selected state target."""

    source_state_node_id: int
    state_node_id: int
    state_node_code: str
    state_node_name: str
    feature_key: str
    operator: str
    target_value: Optional[str] = None
    source_path: list[LayeredPathItem] = Field(default_factory=list)


class LayeredCandidateActivity(BaseModel):
    """Expanded level-3 candidate activity from a selected activity scope."""

    source_activity_node_id: int
    activity_node_id: int
    activity_node_code: str
    activity_node_name: str
    activity_category: str
    node_type: str = "legacy_activity_node"
    atomic_activity_id: Optional[int] = None
    activity_package_atomic_ref_id: Optional[int] = None
    op_rule_ids: list[int] = Field(default_factory=list)
    source_path: list[LayeredPathItem] = Field(default_factory=list)


class EffectiveRulePrecondition(BaseModel):
    """Effective precondition with explicit source metadata."""

    source_type: str
    feature_key: Optional[str] = None
    operator: str
    feature_value: Optional[str] = None
    value_list: Optional[list[Any]] = None
    state_node_id: Optional[int] = None
    state_node_code: Optional[str] = None
    state_node_name: Optional[str] = None
    scope_guard_id: Optional[int] = None
    scope_guard_name: Optional[str] = None
    source_activity_node_id: Optional[int] = None
    source_activity_node_code: Optional[str] = None


class EffectiveRuleEffect(BaseModel):
    """Effect owned by the executable op rule."""

    feature_key: str
    new_value: str
    effect_type: str = "set"
    delta_value: Optional[float] = None


class EffectiveRuleResourceReq(BaseModel):
    """Resource requirement owned by the executable op rule."""

    resource_type: str
    quantity: int
    is_required: bool = True


class EffectiveRulePreview(BaseModel):
    """Preview of an op rule after Scope Guard expansion."""

    op_rule_id: int
    op_rule_code: str
    op_rule_name: str
    activity_node_id: int
    activity_node_code: str
    activity_node_name: str
    atomic_activity_id: Optional[int] = None
    duration_min: int
    preconditions: list[EffectiveRulePrecondition] = Field(default_factory=list)
    effects: list[EffectiveRuleEffect] = Field(default_factory=list)
    resource_reqs: list[EffectiveRuleResourceReq] = Field(default_factory=list)


class LayeredExpansionDiagnostic(BaseModel):
    """Non-fatal diagnostic returned by layered expansion preview."""

    code: str
    message: str
    node_id: Optional[int] = None
    node_type: Optional[str] = None
    severity: str = "warning"


class LayeredExpansionResponse(BaseModel):
    """Response for layered target/activity expansion preview."""

    machine_type_id: int
    goal_facts: list[LayeredGoalFact] = Field(default_factory=list)
    candidate_activities: list[LayeredCandidateActivity] = Field(default_factory=list)
    effective_rules: list[EffectiveRulePreview] = Field(default_factory=list)
    diagnostics: list[LayeredExpansionDiagnostic] = Field(default_factory=list)


class LayeredHealthProvider(BaseModel):
    """One candidate op rule that can provide a fact."""

    op_rule_id: int
    op_rule_code: str
    activity_node_id: int
    activity_node_code: str
    atomic_activity_id: Optional[int] = None
    source_activity_node_id: Optional[int] = None


class LayeredHealthConsumer(BaseModel):
    """One effective precondition that consumes a fact."""

    op_rule_id: int
    op_rule_code: str
    activity_node_id: int
    activity_node_code: str
    atomic_activity_id: Optional[int] = None
    source_type: str
    scope_guard_id: Optional[int] = None
    scope_guard_name: Optional[str] = None
    source_activity_node_id: Optional[int] = None


class LayeredHealthFactNode(BaseModel):
    """Provider/consumer graph node keyed by a concrete fact value."""

    feature_key: str
    target_value: str
    goal_state_node_ids: list[int] = Field(default_factory=list)
    providers: list[LayeredHealthProvider] = Field(default_factory=list)
    consumers: list[LayeredHealthConsumer] = Field(default_factory=list)


class LayeredHealthDiagnostic(BaseModel):
    """Reachability or rule-health diagnostic for layered planning data."""

    code: str
    severity: str = "error"
    message: str
    feature_key: Optional[str] = None
    operator: Optional[str] = None
    target_value: Optional[str] = None
    op_rule_id: Optional[int] = None
    activity_node_id: Optional[int] = None
    state_node_id: Optional[int] = None
    source_type: Optional[str] = None
    provider_count: Optional[int] = None
    details: Optional[dict[str, Any]] = None


class LayeredHealthSummary(BaseModel):
    """High-level counts for a layered health-check response."""

    goal_fact_count: int
    candidate_activity_count: int
    effective_rule_count: int
    provider_fact_count: int
    consumer_fact_count: int
    diagnostic_count: int
    blocking_count: int


class LayeredHealthCheckResponse(BaseModel):
    """Response for layered Provider/Consumer health checks."""

    machine_type_id: int
    status: str
    summary: LayeredHealthSummary
    goal_facts: list[LayeredGoalFact] = Field(default_factory=list)
    candidate_activities: list[LayeredCandidateActivity] = Field(default_factory=list)
    effective_rules: list[EffectiveRulePreview] = Field(default_factory=list)
    provider_graph: list[LayeredHealthFactNode] = Field(default_factory=list)
    diagnostics: list[LayeredHealthDiagnostic] = Field(default_factory=list)


class NetworkEditorRequest(BaseModel):
    """Selection and display options for network-editor projections."""

    state_root_ids: list[int] = Field(default_factory=list, description="Selected state roots")
    activity_scope_node_ids: list[int] = Field(default_factory=list, description="Selected activity scopes")
    view_mode: str = Field(default="outline", pattern="^(outline|implementation|solver_ready)$")
    include_inactive: bool = Field(default=False, description="Whether inactive nodes are included")
    state_depth: int = Field(default=0, ge=0, le=32, description="Visible state depth from selected roots; 0 means unlimited")
    activity_depth: int = Field(default=0, ge=0, le=32, description="Visible activity depth from selected scopes; 0 means unlimited")


class NetworkEditorDraftChange(BaseModel):
    """One queued edit-session mutation for unified network-editor submit."""

    client_id: Optional[str] = Field(None, min_length=1, max_length=128)
    entity_type: str = Field(..., min_length=1, max_length=64)
    operation: str = Field(..., min_length=1, max_length=32)
    entity_id: Optional[int] = Field(None, gt=0)
    payload: dict[str, Any] = Field(default_factory=dict)
    label: Optional[str] = Field(None, max_length=256)


class NetworkEditorCommitRequest(BaseModel):
    """Apply an edit-session draft as one database request."""

    changes: list[NetworkEditorDraftChange] = Field(default_factory=list)
    base_revision: Optional[str] = Field(None, min_length=1, max_length=128)
    validate_after_apply: bool = Field(default=True)
    allow_warnings: bool = Field(default=True)
    validation_payload: NetworkEditorRequest = Field(default_factory=NetworkEditorRequest)


class NetworkEditorCommitResponse(BaseModel):
    """Result of a unified network-editor submit."""

    machine_type_id: int
    applied_change_count: int
    results: list[dict[str, Any]] = Field(default_factory=list)
    validation: Optional[dict[str, Any]] = None
    revision: Optional[str] = None


class NetworkEditorImpactRequest(NetworkEditorRequest):
    """Selection request for network-editor impact analysis."""

    state_node_id: Optional[int] = Field(default=None, gt=0)
    activity_graph_id: Optional[str] = Field(default=None, min_length=1)


class NetworkEditorIssue(BaseModel):
    """Modeling or solver-readiness issue returned by the network editor."""

    id: str
    code: str
    severity: str
    category: str
    message: str
    related_state_ids: list[int] = Field(default_factory=list)
    related_activity_ids: list[str] = Field(default_factory=list)
    details: Optional[dict[str, Any]] = None
    suggested_action: Optional[str] = None


class NetworkEditorGraphResponse(BaseModel):
    """Projected state/activity graph for the network editor."""

    machine_type_id: int
    revision: Optional[str] = None
    view_mode: str
    state_nodes: list[dict[str, Any]] = Field(default_factory=list)
    activity_nodes: list[dict[str, Any]] = Field(default_factory=list)
    bindings: list[dict[str, Any]] = Field(default_factory=list)
    edges: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    validation_summary: dict[str, Any] = Field(default_factory=dict)


class NetworkEditorValidationResponse(BaseModel):
    """Split modeling and solver-ready validation result."""

    machine_type_id: int
    status: str
    summary: dict[str, Any] = Field(default_factory=dict)
    modeling_issues: list[NetworkEditorIssue] = Field(default_factory=list)
    solver_ready_issues: list[NetworkEditorIssue] = Field(default_factory=list)


class NetworkEditorImpactResponse(BaseModel):
    """Read-only impact analysis for a selected state or activity graph node."""

    machine_type_id: int
    view_mode: str
    selection_type: str
    selection_id: str
    status: str
    selected: dict[str, Any] = Field(default_factory=dict)
    summary: dict[str, Any] = Field(default_factory=dict)
    parent_state_chain: list[dict[str, Any]] = Field(default_factory=list)
    child_coverage: dict[str, Any] = Field(default_factory=dict)
    reference_parent_states: list[dict[str, Any]] = Field(default_factory=list)
    upstream_activities: list[dict[str, Any]] = Field(default_factory=list)
    downstream_activities: list[dict[str, Any]] = Field(default_factory=list)
    direct_precondition_states: list[dict[str, Any]] = Field(default_factory=list)
    inherited_precondition_states: list[dict[str, Any]] = Field(default_factory=list)
    output_states: list[dict[str, Any]] = Field(default_factory=list)
    owner_virtual_activities: list[dict[str, Any]] = Field(default_factory=list)
    affected_parent_states: list[dict[str, Any]] = Field(default_factory=list)
    affected_virtual_activities: list[dict[str, Any]] = Field(default_factory=list)
    affected_executable_activities: list[dict[str, Any]] = Field(default_factory=list)
    package_bindings: list[dict[str, Any]] = Field(default_factory=list)
    bindings: list[dict[str, Any]] = Field(default_factory=list)
    participates_in_solver: Optional[bool] = None
    issues: list[NetworkEditorIssue] = Field(default_factory=list)


class NetworkEditorSolverPrecheckResponse(BaseModel):
    """Solver readiness precheck projection without launching the Scheduler."""

    machine_type_id: int
    status: str
    summary: dict[str, Any] = Field(default_factory=dict)
    executable_activities: list[dict[str, Any]] = Field(default_factory=list)
    excluded_virtual_activities: list[dict[str, Any]] = Field(default_factory=list)
    virtual_activity_groups: list[dict[str, Any]] = Field(default_factory=list)
    state_aggregation_rules: list[dict[str, Any]] = Field(default_factory=list)
    blocking_issues: list[NetworkEditorIssue] = Field(default_factory=list)
    request_preview: dict[str, Any] = Field(default_factory=dict)
    solve_request_template: dict[str, Any] = Field(default_factory=dict)
    goal_facts: list[dict[str, Any]] = Field(default_factory=list)
    candidate_activities: list[dict[str, Any]] = Field(default_factory=list)
    effective_rules: list[dict[str, Any]] = Field(default_factory=list)
    layered_health_summary: dict[str, Any] = Field(default_factory=dict)
    layered_health_diagnostics: list[dict[str, Any]] = Field(default_factory=list)


class NetworkEditorExportPreviewResponse(NetworkEditorSolverPrecheckResponse):
    """Deprecated compatibility response for the legacy export-preview endpoint."""


class MaintenanceFactTemplate(BaseModel):
    """Exact or predicate fact used by maintenance intent templates."""

    feature_key: str = Field(..., min_length=1, max_length=64)
    operator: str = Field(default="eq", max_length=16)
    value: Optional[str] = Field(None, max_length=256)
    value_list: Optional[list[Any]] = None


class MaintenanceIntentTemplateCreate(BaseModel):
    """Schema for creating a maintenance intent template."""

    machine_type_id: int = Field(..., gt=0)
    scope_activity_node_id: int = Field(..., gt=0)
    issue_type: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    target_state_node_ids: list[int] = Field(default_factory=list)
    candidate_activity_scope_ids: list[int] = Field(default_factory=list)
    observed_fact_templates: list[MaintenanceFactTemplate] = Field(default_factory=list)
    desired_fact_templates: list[MaintenanceFactTemplate] = Field(default_factory=list)
    is_active: bool = True
    metadata_json: Optional[dict[str, Any]] = None


class MaintenanceIntentTemplateUpdate(BaseModel):
    """Schema for updating a maintenance intent template."""

    scope_activity_node_id: int = Field(..., gt=0)
    issue_type: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = None
    target_state_node_ids: list[int] = Field(default_factory=list)
    candidate_activity_scope_ids: list[int] = Field(default_factory=list)
    observed_fact_templates: list[MaintenanceFactTemplate] = Field(default_factory=list)
    desired_fact_templates: list[MaintenanceFactTemplate] = Field(default_factory=list)
    is_active: bool = True
    metadata_json: Optional[dict[str, Any]] = None


class MaintenanceIntentTemplateResponse(BaseSchema):
    """Response schema for a maintenance intent template."""

    id: int
    machine_type_id: int
    scope_activity_node_id: int
    issue_type: str
    name: str
    description: Optional[str] = None
    target_state_node_ids: list[int] = Field(default_factory=list)
    candidate_activity_scope_ids: list[int] = Field(default_factory=list)
    observed_fact_templates: list[MaintenanceFactTemplate] = Field(default_factory=list)
    desired_fact_templates: list[MaintenanceFactTemplate] = Field(default_factory=list)
    is_active: bool
    metadata_json: Optional[dict[str, Any]] = None
    created_at: datetime


class MaintenanceSolveRequest(BaseModel):
    """Request for solving one or more maintenance intents jointly."""

    machine_id: int = Field(..., gt=0)
    current_state_id: int = Field(..., gt=0)
    intent_template_ids: list[int] = Field(default_factory=list)
    extra_observed_facts: list[MaintenanceFactTemplate] = Field(default_factory=list)
    extra_desired_facts: list[MaintenanceFactTemplate] = Field(default_factory=list)
    include_inactive: bool = False
    objective: str = Field(default="minimize_makespan")
    objectives: Optional[list[dict[str, Any]]] = None
    constraints: Optional[dict[str, Any]] = None
    parent_plan_id: Optional[int] = Field(None, description="Parent plan ID for replanning")
    blockage_constraints: Optional[dict[str, Any]] = Field(
        None,
        description="Blockage constraints for maintenance replanning",
    )


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


class LayeredSolveRequest(BaseModel):
    """Request for solving from layered target states and activity scopes."""

    machine_id: int = Field(..., gt=0, description="Machine ID")
    current_state_id: int = Field(..., gt=0, description="Current state ID")
    target_state_node_ids: list[int] = Field(default_factory=list, description="Selected layered target state nodes")
    activity_scope_node_ids: list[int] = Field(
        default_factory=list,
        description="Selected activity scope nodes; empty means all active atomic activities",
    )
    include_inactive: bool = Field(default=False, description="Include inactive layered data")
    objective: str = Field(default="minimize_makespan", description="Optimization objective")
    objectives: Optional[list[dict[str, Any]]] = Field(None, description="Objectives array")
    constraints: Optional[dict[str, Any]] = Field(None, description="Constraints")
    parent_plan_id: Optional[int] = Field(None, description="Parent plan ID for replanning")
    blockage_constraints: Optional[dict[str, Any]] = Field(
        None,
        description="Blockage constraints for layered replanning",
    )
    current_state_overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Solve-only observed facts layered over the selected current state",
    )
    direct_goal_facts: list[MaintenanceFactTemplate] = Field(
        default_factory=list,
        description="Additional exact goal facts not backed by state nodes",
    )
    context: Optional[dict[str, Any]] = Field(
        None,
        description="Opaque caller context to persist and echo in layered explanations",
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
    op_rule_name: Optional[str] = Field(None, description="Operation display name")
    start_min: int = Field(..., ge=0, description="Start time in minutes")
    end_min: int = Field(..., ge=0, description="End time in minutes")
    duration_min: int = Field(..., ge=1, description="Duration in minutes")
    predecessors: list[int] = Field(default_factory=list, description="Predecessor step orders")
    resources: list[dict[str, Any]] = Field(default_factory=list, description="Assigned resources")
    resource_type: str = Field(default="NONE", description="Legacy primary resource type")
    resource_reqs: list[dict[str, Any]] = Field(default_factory=list, description="Required resources")
    activity_node_id: Optional[int] = Field(None, description="Activity node ID for layered schedules")
    activity_node_code: Optional[str] = Field(None, description="Activity node code for layered schedules")
    activity_node_level: Optional[int] = Field(None, description="Activity hierarchy level")
    activity_group_id: Optional[int] = Field(None, description="Second-level activity group ID")
    activity_group_code: Optional[str] = Field(None, description="Second-level activity group code")
    activity_group_name: Optional[str] = Field(None, description="Second-level activity group name")
    state_continuity_groups: list[dict[str, Any]] = Field(
        default_factory=list,
        description="State package memberships used by state-lane Gantt and continuity diagnostics",
    )
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
    diagnostics: Optional[dict[str, Any]] = None


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
    op_name: Optional[str] = None
    step_order: Optional[int] = None
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
    activity_node_id: Optional[int] = None
    atomic_activity_id: Optional[int] = None
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
