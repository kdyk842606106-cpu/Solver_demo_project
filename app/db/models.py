"""
SQLAlchemy ORM Models for the State-Driven Process Planning System.

This module defines all database tables according to the schema in Project_introduction.md.
Total: 13 tables for MVP.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    ARRAY,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
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

    # Relationships
    machine_type: Mapped["MachineType"] = relationship(
        "MachineType", back_populates="state_feature_defs"
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

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(64), nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<Resource(id={self.id}, code='{self.code}', name='{self.name}', resource_type='{self.resource_type}')>"


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
    parent_plan: Mapped[Optional["CandidatePlan"]] = relationship(
        "CandidatePlan", foreign_keys=[parent_plan_id]
    )
    candidate_plans: Mapped[list["CandidatePlan"]] = relationship(
        "CandidatePlan", back_populates="solve_request", cascade="all, delete-orphan"
    )
    schedule_results: Mapped[list["ScheduleResult"]] = relationship(
        "ScheduleResult", back_populates="solve_request", cascade="all, delete-orphan"
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
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )  # pending | running | done | failed
    overrides: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
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
        "CandidatePlan", back_populates="solve_request", cascade="all, delete-orphan"
    )
    schedule_results: Mapped[list["ScheduleResult"]] = relationship(
        "ScheduleResult", back_populates="solve_request", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<SolveRequest(id={self.id}, status='{self.status}', objective='{self.objective}')>"


# ============================================================
# 结果相关（2 张表）
# ============================================================


class CandidatePlan(Base):
    """
    候选工序方案表（第一层输出）.

    记录 Planner 生成的 RAG 结构。
    """

    __tablename__ = "candidate_plan"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solve_request_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("solve_request.id", ondelete="CASCADE"), nullable=False
    )
    total_steps: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    search_method: Mapped[str] = mapped_column(
        String(32), nullable=False, default="state_inference"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_plan_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("candidate_plan.id"), nullable=True
    )
    replan_reason: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    # Relationships
    solve_request: Mapped["SolveRequest"] = relationship(
        "SolveRequest", back_populates="candidate_plans"
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
    blocked_step_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("candidate_plan_step.id", ondelete="CASCADE"), nullable=False
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
