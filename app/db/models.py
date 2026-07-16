"""
SQLAlchemy ORM Models for the State-Driven Process Planning System.

The current persistence contract is documented in ``docs/protocols/db.md``.
Total: 30 tables (V0.3).
"""

from datetime import datetime
from typing import Optional
from uuid import uuid4

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


# ============================================================
# 机台与状态相关（5 张表）
# ============================================================


class MachineType(Base):
    """
    机台类型表.

    定义不同类型的机台，如 CNC 车床、铣床等。
    """

    __tablename__ = "machine_type"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scheduling_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    machines: Mapped[list["Machine"]] = relationship(
        "Machine", back_populates="machine_type", cascade="all, delete-orphan"
    )
    state_feature_defs: Mapped[list["StateFeatureDef"]] = relationship(
        "StateFeatureDef", back_populates="machine_type", cascade="all, delete-orphan"
    )
    op_rules: Mapped[list["OpRule"]] = relationship(
        "OpRule", back_populates="machine_type", cascade="all, delete-orphan"
    )
    activity_nodes: Mapped[list["ActivityNode"]] = relationship(
        "ActivityNode", back_populates="machine_type", cascade="all, delete-orphan"
    )
    atomic_activities: Mapped[list["AtomicActivity"]] = relationship(
        "AtomicActivity", back_populates="machine_type", cascade="all, delete-orphan"
    )
    state_nodes: Mapped[list["StateNode"]] = relationship(
        "StateNode", back_populates="machine_type", cascade="all, delete-orphan"
    )
    activity_state_bindings: Mapped[list["ActivityStateBinding"]] = relationship(
        "ActivityStateBinding", back_populates="machine_type", cascade="all, delete-orphan"
    )
    maintenance_intent_templates: Mapped[list["MaintenanceIntentTemplate"]] = relationship(
        "MaintenanceIntentTemplate", back_populates="machine_type", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<MachineType(id={self.id}, code='{self.code}', name='{self.name}')>"


class Machine(Base):
    """
    机台实例表.

    记录具体的机台实例，关联到机台类型。
    """

    __tablename__ = "machine"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine_type.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    default_work_calendar_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("work_calendar.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    machine_type: Mapped["MachineType"] = relationship(
        "MachineType", back_populates="machines"
    )
    machine_states: Mapped[list["MachineState"]] = relationship(
        "MachineState", back_populates="machine", cascade="all, delete-orphan"
    )
    solve_requests: Mapped[list["SolveRequest"]] = relationship(
        "SolveRequest", back_populates="machine", cascade="all, delete-orphan"
    )
    resources: Mapped[list["Resource"]] = relationship(
        "Resource", back_populates="machine", cascade="all, delete-orphan"
    )
    default_work_calendar: Mapped[Optional["WorkCalendar"]] = relationship(
        "WorkCalendar", foreign_keys=[default_work_calendar_id]
    )
    dimension_calendar_bindings: Mapped[list["MachineStateDimensionCalendar"]] = relationship(
        "MachineStateDimensionCalendar", back_populates="machine", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Machine(id={self.id}, code='{self.code}', name='{self.name}')>"


class StateFeatureDef(Base):
    """
    状态特征定义表.

    描述某种机台类型的状态由哪些维度构成。
    例如：温度等级、清洁度、校准状态等。
    """

    __tablename__ = "state_feature_def"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine_type.id", ondelete="CASCADE"), nullable=False
    )
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)  # string | number | boolean | enum
    allowed_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    is_dimension_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dimension_template_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("state_feature_def.id", ondelete="SET NULL"), nullable=True
    )

    # Relationships
    machine_type: Mapped["MachineType"] = relationship(
        "MachineType", back_populates="state_feature_defs"
    )
    dimension_template: Mapped[Optional["StateFeatureDef"]] = relationship(
        "StateFeatureDef", remote_side=[id], foreign_keys=[dimension_template_id]
    )

    def __repr__(self) -> str:
        return f"<StateFeatureDef(id={self.id}, feature_key='{self.feature_key}', value_type='{self.value_type}')>"


class MachineState(Base):
    """
    机台状态快照表.

    记录机台在某一时刻的状态快照，包括当前状态、目标状态等。
    """

    __tablename__ = "machine_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine.id", ondelete="CASCADE"), nullable=False
    )
    state_type: Mapped[str] = mapped_column(String(32), nullable=False)  # current | target | snapshot
    label: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    machine: Mapped["Machine"] = relationship("Machine", back_populates="machine_states")
    features: Mapped[list["MachineStateFeature"]] = relationship(
        "MachineStateFeature", back_populates="machine_state", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<MachineState(id={self.id}, state_type='{self.state_type}', label='{self.label}')>"


class MachineStateFeature(Base):
    """
    机台状态特征值表.

    记录状态快照的具体特征值，如 temperature_level=cold。
    """

    __tablename__ = "machine_state_feature"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_state_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine_state.id", ondelete="CASCADE"), nullable=False
    )
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_value: Mapped[str] = mapped_column(String(256), nullable=False)

    # Relationships
    machine_state: Mapped["MachineState"] = relationship(
        "MachineState", back_populates="features"
    )

    def __repr__(self) -> str:
        return f"<MachineStateFeature(id={self.id}, feature_key='{self.feature_key}', feature_value='{self.feature_value}')>"


# ============================================================
# 工序规则相关（4 张表）
# ============================================================


class OpRule(Base):
    """
    工序规则主表.

    定义可执行的工序，包含前置条件、执行效果、资源需求等。
    """

    __tablename__ = "op_rule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine_type.id", ondelete="CASCADE"), nullable=False
    )
    activity_node_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("activity_node.id", ondelete="SET NULL"), nullable=True
    )
    atomic_activity_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("atomic_activity.id", ondelete="SET NULL"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    duration_min: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_repair: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_to: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    machine_type: Mapped["MachineType"] = relationship(
        "MachineType", back_populates="op_rules"
    )
    preconditions: Mapped[list["OpRulePrecond"]] = relationship(
        "OpRulePrecond", back_populates="op_rule", cascade="all, delete-orphan"
    )
    effects: Mapped[list["OpRuleEffect"]] = relationship(
        "OpRuleEffect", back_populates="op_rule", cascade="all, delete-orphan"
    )
    resource_reqs: Mapped[list["OpRuleResourceReq"]] = relationship(
        "OpRuleResourceReq", back_populates="op_rule", cascade="all, delete-orphan"
    )
    activity_node: Mapped[Optional["ActivityNode"]] = relationship(
        "ActivityNode", back_populates="op_rules"
    )
    atomic_activity: Mapped[Optional["AtomicActivity"]] = relationship(
        "AtomicActivity", back_populates="op_rules"
    )
    activity_state_bindings: Mapped[list["ActivityStateBinding"]] = relationship(
        "ActivityStateBinding", back_populates="op_rule"
    )

    def __repr__(self) -> str:
        return f"<OpRule(id={self.id}, code='{self.code}', name='{self.name}', duration_min={self.duration_min})>"


class OpRulePrecond(Base):
    """
    工序前提条件表.

    定义执行某工序前，机台状态必须满足的特征值。
    """

    __tablename__ = "op_rule_precond"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    op_rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("op_rule.id", ondelete="CASCADE"), nullable=False
    )
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    operator: Mapped[str] = mapped_column(String(16), nullable=False, default="eq")
    feature_value: Mapped[str] = mapped_column(String(256), nullable=False)
    value_list: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    # Relationships
    op_rule: Mapped["OpRule"] = relationship("OpRule", back_populates="preconditions")

    def __repr__(self) -> str:
        return f"<OpRulePrecond(id={self.id}, feature_key='{self.feature_key}', operator='{self.operator}', feature_value='{self.feature_value}')>"


class OpRuleEffect(Base):
    """
    工序执行效果表.

    定义执行某工序后，机台状态特征值如何变化。
    """

    __tablename__ = "op_rule_effect"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    op_rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("op_rule.id", ondelete="CASCADE"), nullable=False
    )
    feature_key: Mapped[str] = mapped_column(String(64), nullable=False)
    new_value: Mapped[str] = mapped_column(String(256), nullable=False)
    effect_type: Mapped[str] = mapped_column(String(32), nullable=False, default="set")
    delta_value: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)

    # Relationships
    op_rule: Mapped["OpRule"] = relationship("OpRule", back_populates="effects")

    def __repr__(self) -> str:
        return f"<OpRuleEffect(id={self.id}, feature_key='{self.feature_key}', new_value='{self.new_value}')>"


class OpRuleResourceReq(Base):
    """
    工序资源需求表.

    定义执行某工序需要哪些资源。
    """

    __tablename__ = "op_rule_resource_req"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    op_rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("op_rule.id", ondelete="CASCADE"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    op_rule: Mapped["OpRule"] = relationship("OpRule", back_populates="resource_reqs")

    def __repr__(self) -> str:
        return f"<OpRuleResourceReq(id={self.id}, resource_type='{self.resource_type}', quantity={self.quantity})>"


# ============================================================
# 资源相关（1 张表）
# ============================================================


class Resource(Base):
    """
    资源表.

    记录人员、工具、辅助设备等资源。
    """

    __tablename__ = "resource"
    __table_args__ = (
        UniqueConstraint("machine_id", "code", name="uq_resource_machine_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    machine: Mapped["Machine"] = relationship("Machine", back_populates="resources")

    def __repr__(self) -> str:
        return f"<Resource(id={self.id}, code='{self.code}', name='{self.name}', resource_type='{self.resource_type}')>"


class WorkCalendar(Base):
    """Reusable work-calendar identity whose definitions are immutable revisions."""

    __tablename__ = "work_calendar"
    __table_args__ = (
        Index(
            "uq_work_calendar_single_system_default",
            "is_system_default",
            unique=True,
            postgresql_where=text("is_system_default"),
            sqlite_where=text("is_system_default = 1"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_system_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    current_revision_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("work_calendar_revision.id", ondelete="SET NULL", use_alter=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    revisions: Mapped[list["WorkCalendarRevision"]] = relationship(
        "WorkCalendarRevision",
        back_populates="calendar",
        cascade="all, delete-orphan",
        foreign_keys="WorkCalendarRevision.work_calendar_id",
    )
    current_revision: Mapped[Optional["WorkCalendarRevision"]] = relationship(
        "WorkCalendarRevision", foreign_keys=[current_revision_id], post_update=True
    )


class WorkCalendarRevision(Base):
    """Immutable work-calendar definition."""

    __tablename__ = "work_calendar_revision"
    __table_args__ = (
        UniqueConstraint("work_calendar_id", "revision_no", name="uq_work_calendar_revision_no"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    work_calendar_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("work_calendar.id", ondelete="CASCADE"), nullable=False
    )
    revision_no: Mapped[int] = mapped_column(Integer, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    weekly_windows: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    date_exceptions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    calendar: Mapped["WorkCalendar"] = relationship(
        "WorkCalendar", back_populates="revisions", foreign_keys=[work_calendar_id]
    )


class MachineStateDimensionCalendar(Base):
    """Per-machine mapping from a state dimension template to a work calendar."""

    __tablename__ = "machine_state_dimension_calendar"
    __table_args__ = (
        UniqueConstraint(
            "machine_id", "state_dimension_template_id", name="uq_machine_state_dimension_calendar"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine.id", ondelete="CASCADE"), nullable=False
    )
    state_dimension_template_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("state_feature_def.id", ondelete="CASCADE"), nullable=False
    )
    work_calendar_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("work_calendar.id", ondelete="RESTRICT"), nullable=False
    )

    machine: Mapped["Machine"] = relationship("Machine", back_populates="dimension_calendar_bindings")
    state_dimension_template: Mapped["StateFeatureDef"] = relationship("StateFeatureDef")
    work_calendar: Mapped["WorkCalendar"] = relationship("WorkCalendar")


class FeatureDefinition(Base):
    """
    特征类型定义表.

    定义系统中所有可用的特征类型，用于前置条件匹配和效果应用。
    """

    __tablename__ = "feature_definition"

    feature_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value_type: Mapped[str] = mapped_column(String(32), nullable=False)
    allowed_values: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<FeatureDefinition(feature_key='{self.feature_key}', value_type='{self.value_type}')>"


# ============================================================
# 分层活动 / 分层状态（Phase 1 数据底座）
# ============================================================


class ActivityNode(Base):
    """
    活动层级节点表.

    一级 / 二级节点用于业务组织、Scope Guard 和展示；三级节点可关联
    OpRule，作为最终可执行活动的业务归属。
    """

    __tablename__ = "activity_node"
    __table_args__ = (
        CheckConstraint("level IN (1, 2, 3)", name="ck_activity_node_level"),
        UniqueConstraint("machine_type_id", "code", name="uq_activity_node_machine_type_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine_type.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("activity_node.id", ondelete="CASCADE"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activity_category: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    machine_type: Mapped["MachineType"] = relationship(
        "MachineType", back_populates="activity_nodes"
    )
    parent: Mapped[Optional["ActivityNode"]] = relationship(
        "ActivityNode", remote_side=[id], back_populates="children"
    )
    children: Mapped[list["ActivityNode"]] = relationship(
        "ActivityNode", back_populates="parent", cascade="all, delete-orphan"
    )
    op_rules: Mapped[list["OpRule"]] = relationship(
        "OpRule", back_populates="activity_node"
    )
    scope_guards: Mapped[list["ScopeGuard"]] = relationship(
        "ScopeGuard", back_populates="activity_node", cascade="all, delete-orphan"
    )
    atomic_refs: Mapped[list["ActivityPackageAtomicRef"]] = relationship(
        "ActivityPackageAtomicRef", back_populates="activity_node", cascade="all, delete-orphan"
    )
    activity_state_bindings: Mapped[list["ActivityStateBinding"]] = relationship(
        "ActivityStateBinding", back_populates="activity_node", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ActivityNode(id={self.id}, level={self.level}, code='{self.code}')>"


class AtomicActivity(Base):
    """
    可复用原子活动定义.

    原子活动是真正可执行的能力；二级活动包通过引用表复用它。
    """

    __tablename__ = "atomic_activity"
    __table_args__ = (
        UniqueConstraint("machine_type_id", "code", name="uq_atomic_activity_machine_type_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine_type.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    activity_category: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    machine_type: Mapped["MachineType"] = relationship(
        "MachineType", back_populates="atomic_activities"
    )
    package_refs: Mapped[list["ActivityPackageAtomicRef"]] = relationship(
        "ActivityPackageAtomicRef", back_populates="atomic_activity", cascade="all, delete-orphan"
    )
    op_rules: Mapped[list["OpRule"]] = relationship(
        "OpRule", back_populates="atomic_activity"
    )
    activity_state_bindings: Mapped[list["ActivityStateBinding"]] = relationship(
        "ActivityStateBinding", back_populates="atomic_activity", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<AtomicActivity(id={self.id}, code='{self.code}')>"


class ActivityPackageAtomicRef(Base):
    """二级活动包到原子活动的复用引用."""

    __tablename__ = "activity_package_atomic_ref"
    __table_args__ = (
        UniqueConstraint("activity_node_id", "atomic_activity_id", name="uq_activity_package_atomic_ref"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("activity_node.id", ondelete="CASCADE"), nullable=False
    )
    atomic_activity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("atomic_activity.id", ondelete="RESTRICT"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    activity_node: Mapped["ActivityNode"] = relationship(
        "ActivityNode", back_populates="atomic_refs"
    )
    atomic_activity: Mapped["AtomicActivity"] = relationship(
        "AtomicActivity", back_populates="package_refs"
    )

    def __repr__(self) -> str:
        return f"<ActivityPackageAtomicRef(activity_node_id={self.activity_node_id}, atomic_activity_id={self.atomic_activity_id})>"


class StateNode(Base):
    """
    状态层级节点表.

    一级 / 二级状态为聚合状态；三级状态为可判定叶子状态。
    """

    __tablename__ = "state_node"
    __table_args__ = (
        CheckConstraint("level >= 1", name="ck_state_node_level_positive"),
        UniqueConstraint("machine_type_id", "code", name="uq_state_node_machine_type_code"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine_type.id", ondelete="CASCADE"), nullable=False
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("state_node.id", ondelete="CASCADE"), nullable=True
    )
    level: Mapped[int] = mapped_column(Integer, nullable=False)
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_key: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    operator: Mapped[str] = mapped_column(String(16), nullable=False, default="eq")
    target_value: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    state_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="aggregate")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    machine_type: Mapped["MachineType"] = relationship(
        "MachineType", back_populates="state_nodes"
    )
    parent: Mapped[Optional["StateNode"]] = relationship(
        "StateNode", remote_side=[id], back_populates="children"
    )
    children: Mapped[list["StateNode"]] = relationship(
        "StateNode", back_populates="parent", cascade="all, delete-orphan"
    )
    references_as_state: Mapped[list["StateNodeReference"]] = relationship(
        "StateNodeReference",
        back_populates="state_node",
        cascade="all, delete-orphan",
        foreign_keys="StateNodeReference.state_node_id",
    )
    references_as_parent: Mapped[list["StateNodeReference"]] = relationship(
        "StateNodeReference",
        back_populates="parent_state_node",
        cascade="all, delete-orphan",
        foreign_keys="StateNodeReference.parent_state_node_id",
    )
    activity_state_bindings: Mapped[list["ActivityStateBinding"]] = relationship(
        "ActivityStateBinding", back_populates="state_node", cascade="all, delete-orphan"
    )
    scope_guard_preconditions: Mapped[list["ScopeGuardPrecond"]] = relationship(
        "ScopeGuardPrecond", back_populates="state_node"
    )

    def __repr__(self) -> str:
        return f"<StateNode(id={self.id}, level={self.level}, code='{self.code}')>"


class StateNodeReference(Base):
    """Additional display parent for a state node."""

    __tablename__ = "state_node_reference"
    __table_args__ = (
        UniqueConstraint("state_node_id", "parent_state_node_id", name="uq_state_node_reference_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    state_node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("state_node.id", ondelete="CASCADE"), nullable=False
    )
    parent_state_node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("state_node.id", ondelete="CASCADE"), nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    state_node: Mapped["StateNode"] = relationship(
        "StateNode",
        back_populates="references_as_state",
        foreign_keys=[state_node_id],
    )
    parent_state_node: Mapped["StateNode"] = relationship(
        "StateNode",
        back_populates="references_as_parent",
        foreign_keys=[parent_state_node_id],
    )

    def __repr__(self) -> str:
        return (
            "<StateNodeReference("
            f"state_node_id={self.state_node_id}, parent_state_node_id={self.parent_state_node_id})>"
        )


class ActivityStateBinding(Base):
    """State/activity semantic binding used by the network editor."""

    __tablename__ = "activity_state_binding"
    __table_args__ = (
        CheckConstraint(
            "(activity_node_id IS NOT NULL AND atomic_activity_id IS NULL) "
            "OR (activity_node_id IS NULL AND atomic_activity_id IS NOT NULL)",
            name="ck_activity_state_binding_one_activity_identity",
        ),
        CheckConstraint(
            "binding_role IN ('input', 'output', 'context_input', 'declared_output')",
            name="ck_activity_state_binding_role",
        ),
        CheckConstraint(
            "binding_type IN ('state_package', 'atomic_state')",
            name="ck_activity_state_binding_type",
        ),
        CheckConstraint(
            "coverage_policy IN ('snapshot')",
            name="ck_activity_state_binding_coverage_policy",
        ),
        CheckConstraint(
            "coverage_status IN ('complete', 'partial', 'stale')",
            name="ck_activity_state_binding_coverage_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine_type.id", ondelete="CASCADE"), nullable=False
    )
    activity_node_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("activity_node.id", ondelete="CASCADE"), nullable=True
    )
    atomic_activity_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("atomic_activity.id", ondelete="CASCADE"), nullable=True
    )
    op_rule_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("op_rule.id", ondelete="SET NULL"), nullable=True
    )
    state_node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("state_node.id", ondelete="CASCADE"), nullable=False
    )
    binding_role: Mapped[str] = mapped_column(String(32), nullable=False)
    binding_type: Mapped[str] = mapped_column(String(32), nullable=False)
    coverage_policy: Mapped[str] = mapped_column(String(32), nullable=False, default="snapshot")
    covered_leaf_state_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    coverage_status: Mapped[str] = mapped_column(String(32), nullable=False, default="stale")
    is_inherited: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    machine_type: Mapped["MachineType"] = relationship(
        "MachineType", back_populates="activity_state_bindings"
    )
    activity_node: Mapped[Optional["ActivityNode"]] = relationship(
        "ActivityNode", back_populates="activity_state_bindings"
    )
    atomic_activity: Mapped[Optional["AtomicActivity"]] = relationship(
        "AtomicActivity", back_populates="activity_state_bindings"
    )
    op_rule: Mapped[Optional["OpRule"]] = relationship(
        "OpRule", back_populates="activity_state_bindings"
    )
    state_node: Mapped["StateNode"] = relationship(
        "StateNode", back_populates="activity_state_bindings"
    )

    def __repr__(self) -> str:
        return (
            f"<ActivityStateBinding(id={self.id}, role='{self.binding_role}', "
            f"state_node_id={self.state_node_id})>"
        )


class ScopeGuard(Base):
    """
    作用域公共前置约束.

    Scope Guard 只能挂在一级或二级活动上，只表达 precondition，不表达
    effect / duration / resource requirement。
    """

    __tablename__ = "scope_guard"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    activity_node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("activity_node.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    activity_node: Mapped["ActivityNode"] = relationship(
        "ActivityNode", back_populates="scope_guards"
    )
    preconditions: Mapped[list["ScopeGuardPrecond"]] = relationship(
        "ScopeGuardPrecond", back_populates="scope_guard", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<ScopeGuard(id={self.id}, activity_node_id={self.activity_node_id}, name='{self.name}')>"


class ScopeGuardPrecond(Base):
    """A single state-node precondition inside a Scope Guard."""

    __tablename__ = "scope_guard_precond"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scope_guard_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("scope_guard.id", ondelete="CASCADE"), nullable=False
    )
    state_node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("state_node.id", ondelete="RESTRICT"), nullable=False
    )
    operator: Mapped[str] = mapped_column(String(16), nullable=False, default="completed")
    expected_value: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    value_list: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    scope_guard: Mapped["ScopeGuard"] = relationship(
        "ScopeGuard", back_populates="preconditions"
    )
    state_node: Mapped["StateNode"] = relationship(
        "StateNode", back_populates="scope_guard_preconditions"
    )

    def __repr__(self) -> str:
        return f"<ScopeGuardPrecond(id={self.id}, state_node_id={self.state_node_id}, operator='{self.operator}')>"


class MaintenanceIntentTemplate(Base):
    """
    维修维护意图模板表.

    模板表达维修维护意图对应的目标事实和候选活动范围，不表达固定执行序列。
    """

    __tablename__ = "maintenance_intent_template"
    __table_args__ = (
        UniqueConstraint("machine_type_id", "issue_type", name="uq_maintenance_intent_machine_type_issue"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_type_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine_type.id", ondelete="CASCADE"), nullable=False
    )
    scope_activity_node_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("activity_node.id", ondelete="RESTRICT"), nullable=False
    )
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_state_node_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    candidate_activity_scope_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    observed_fact_templates: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    desired_fact_templates: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    machine_type: Mapped["MachineType"] = relationship(
        "MachineType", back_populates="maintenance_intent_templates"
    )
    scope_activity_node: Mapped["ActivityNode"] = relationship("ActivityNode")

    def __repr__(self) -> str:
        return f"<MaintenanceIntentTemplate(id={self.id}, issue_type='{self.issue_type}')>"


# ============================================================
# 求解请求相关（1 张表）
# ============================================================


class SolveRequest(Base):
    """
    求解请求表.

    记录用户的求解请求，包含当前状态、目标状态、优化目标等。
    """

    __tablename__ = "solve_request"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine.id", ondelete="CASCADE"), nullable=False
    )
    current_state_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine_state.id", ondelete="RESTRICT"), nullable=False
    )
    target_state_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine_state.id", ondelete="RESTRICT"), nullable=False
    )
    objective: Mapped[str] = mapped_column(
        String(64), nullable=False, default="minimize_makespan"
    )
    objectives: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    constraints: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    parent_plan_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("candidate_plan.id"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    overrides: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    blockage_constraints: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    calendar_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    schedule_start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    schedule_timezone: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    calendar_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    solved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    machine: Mapped["Machine"] = relationship("Machine", back_populates="solve_requests")
    current_state: Mapped["MachineState"] = relationship(
        "MachineState", foreign_keys=[current_state_id]
    )
    target_state: Mapped["MachineState"] = relationship(
        "MachineState", foreign_keys=[target_state_id]
    )
    candidate_plans: Mapped[list["CandidatePlan"]] = relationship(
        "CandidatePlan",
        back_populates="solve_request",
        cascade="all, delete-orphan",
        primaryjoin="CandidatePlan.solve_request_id == SolveRequest.id"
    )
    schedule_results: Mapped[list["ScheduleResult"]] = relationship(
        "ScheduleResult", back_populates="solve_request", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SolveRequest(id={self.id}, status='{self.status}', objective='{self.objective}')>"


# ============================================================
# 计划版本与结果相关
# ============================================================


class PlanFamily(Base):
    """Immutable plan-version chain with one selected planning baseline.

    ``baseline_plan_id`` is deliberately a scalar reference instead of an ORM
    relationship.  This avoids adding another SQLAlchemy dependency cycle to
    the historical SolveRequest/CandidatePlan cycle while still allowing the
    service layer to switch the baseline atomically under a row lock.
    """

    __tablename__ = "plan_family"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("machine.id", ondelete="CASCADE"), nullable=False
    )
    baseline_plan_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    next_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class CandidatePlan(Base):
    """
    候选工序方案表（第一层输出）.

    记录 Planner 生成的 RAG 结构。
    """

    __tablename__ = "candidate_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_family_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("plan_family.id", ondelete="SET NULL"), nullable=True, index=True
    )
    solve_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("solve_request.id", ondelete="CASCADE"), nullable=False
    )
    total_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    search_method: Mapped[str] = mapped_column(
        String(32), nullable=False, default="partial_order"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_plan_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("candidate_plan.id"), nullable=True
    )
    replan_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    adjustment_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    solve_request: Mapped["SolveRequest"] = relationship(
        "SolveRequest", back_populates="candidate_plans", foreign_keys=[solve_request_id]
    )
    steps: Mapped[list["CandidatePlanStep"]] = relationship(
        "CandidatePlanStep", back_populates="candidate_plan", cascade="all, delete-orphan"
    )
    schedule_results: Mapped[list["ScheduleResult"]] = relationship(
        "ScheduleResult", back_populates="candidate_plan", cascade="all, delete-orphan"
    )
    blockage_events: Mapped[list["BlockageEvent"]] = relationship(
        "BlockageEvent", back_populates="candidate_plan", cascade="all, delete-orphan"
    )
    parent_plan: Mapped[Optional["CandidatePlan"]] = relationship(
        "CandidatePlan", remote_side=[id], foreign_keys=[parent_plan_id]
    )
    child_plans: Mapped[list["CandidatePlan"]] = relationship(
        "CandidatePlan", back_populates="parent_plan"
    )

    def __repr__(self) -> str:
        return f"<CandidatePlan(id={self.id}, total_steps={self.total_steps}, search_method='{self.search_method}')>"


class CandidatePlanStep(Base):
    """
    候选方案工序步骤表.

    记录 RAG 的每个节点，包含前置依赖关系（来自 precond/effect 推导）。
    """

    __tablename__ = "candidate_plan_step"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    candidate_plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidate_plan.id", ondelete="CASCADE"), nullable=False
    )
    step_order: Mapped[int] = mapped_column(Integer, nullable=False)
    op_rule_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("op_rule.id", ondelete="RESTRICT"), nullable=False
    )
    predecessor_ids: Mapped[Optional[list[int]]] = mapped_column(
        ARRAY(Integer), nullable=True, default=[]
    )
    not_before: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    step_role: Mapped[str] = mapped_column(String(32), nullable=False, default="normal")
    lineage_key: Mapped[str] = mapped_column(
        String(36), nullable=False, default=lambda: str(uuid4()), index=True
    )

    # Relationships
    candidate_plan: Mapped["CandidatePlan"] = relationship(
        "CandidatePlan", back_populates="steps"
    )
    op_rule: Mapped["OpRule"] = relationship("OpRule")

    def __repr__(self) -> str:
        return f"<CandidatePlanStep(id={self.id}, step_order={self.step_order}, op_rule_id={self.op_rule_id}, predecessor_ids={self.predecessor_ids})>"


class ScheduleResult(Base):
    """
    最终调度结果表（第二层输出）.

    记录 Scheduler 生成的排程结果。
    """

    __tablename__ = "schedule_result"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solve_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("solve_request.id", ondelete="CASCADE"), nullable=False
    )
    candidate_plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidate_plan.id", ondelete="RESTRICT"), nullable=False
    )
    makespan: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    solver_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    tasks: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    solve_request: Mapped["SolveRequest"] = relationship(
        "SolveRequest", back_populates="schedule_results"
    )
    candidate_plan: Mapped["CandidatePlan"] = relationship(
        "CandidatePlan", back_populates="schedule_results"
    )

    def __repr__(self) -> str:
        return f"<ScheduleResult(id={self.id}, makespan={self.makespan}, solver_status='{self.solver_status}')>"


class BlockageEvent(Base):
    """
    阻塞事件表.

    记录计划师标记的阻塞事件及处理策略。
    """

    __tablename__ = "blockage_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidate_plan.id", ondelete="CASCADE"), nullable=False
    )
    blocked_step_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("candidate_plan_step.id", ondelete="CASCADE"), nullable=True
    )
    strategy: Mapped[str] = mapped_column(String(8), nullable=False)
    not_before_offset: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    blockage_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # Relationships
    candidate_plan: Mapped["CandidatePlan"] = relationship(
        "CandidatePlan", back_populates="blockage_events"
    )

    def __repr__(self) -> str:
        return f"<BlockageEvent(id={self.id}, strategy='{self.strategy}', blockage_reason='{self.blockage_reason}')>"


class PlanAdjustment(Base):
    """Persisted constraint-editing draft for one immutable baseline plan."""

    __tablename__ = "plan_adjustment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plan_family_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plan_family.id", ondelete="CASCADE"), nullable=False, index=True
    )
    baseline_plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidate_plan.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_plan_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("candidate_plan.id", ondelete="SET NULL"), nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False, default="schedule")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft", index=True)
    scope_step_ids: Mapped[list[int]] = mapped_column(
        ARRAY(Integer), nullable=False, default=list
    )
    constraints: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    remove_inherited_constraint_ids: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list
    )
    effective_constraints: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    preview_summary: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    diagnostics: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    previewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('schedule', 'blockage', 'rule_exception')",
            name="ck_plan_adjustment_kind",
        ),
        CheckConstraint(
            "status IN ('draft', 'previewing', 'preview_ready', 'infeasible', "
            "'confirmed', 'cancelled', 'stale')",
            name="ck_plan_adjustment_status",
        ),
    )
