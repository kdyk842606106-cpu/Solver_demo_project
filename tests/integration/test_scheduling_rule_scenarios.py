"""Realistic end-to-end scenarios for registered integration scheduling rules."""

import pytest
from sqlalchemy import select

from app.core.scheduler.calendar import definition_checksum
from app.db.models import (
    ActivityNode,
    ActivityPackageAtomicRef,
    AtomicActivity,
    CandidatePlan,
    CandidatePlanStep,
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
    SolveRequest,
    StateFeatureDef,
    StateNode,
    WorkCalendar,
    WorkCalendarRevision,
)
from app.db.schemas import LayeredSolveRequest, MaintenanceSolveRequest
from app.services.layered_solve import solve_layered
from app.services.maintenance_solve import solve_maintenance


pytestmark = pytest.mark.asyncio


def _scope_exclusivity_rule(
    code: str,
    selector: dict,
    *,
    mode: str,
    activation_mode: str,
    overridable: bool = False,
    presentation: dict | None = None,
) -> dict:
    rule = {
        "code": code,
        "name": code,
        "type": "scope_exclusivity",
        "enabled": True,
        "activation_mode": activation_mode,
        "selector": selector,
        "enforcement": {"mode": mode, "overridable": overridable},
        "parameters": {"against": "all_other_tasks"},
    }
    if presentation:
        rule["presentation"] = presentation
    return rule


async def _seed_crane_function_test_scenario(session) -> dict[str, int]:
    machine_type = MachineType(
        code="INTEGRATION_RULE_REALISTIC",
        name="集成排期真实规则场景",
        scheduling_config={
            "responsible_subsystems": [
                {"code": "STRUCTURE", "name": "结构子系统"},
                {"code": "CONTROL", "name": "控制子系统"},
            ],
            "rules": [
                _scope_exclusivity_rule(
                    "CRANE_EXCLUSIVE",
                    {"required_resource_type": "OVERHEAD_CRANE"},
                    mode="hard",
                    activation_mode="required",
                    presentation={
                        "gantt_marker": {"text": "吊", "color": "#f59e0b"}
                    },
                ),
                {
                    "code": "CRANE_DAY_SHIFT_ONLY",
                    "name": "行吊仅允许白班",
                    "type": "shift_restriction",
                    "enabled": True,
                    "activation_mode": "required",
                    "selector": {"required_resource_type": "OVERHEAD_CRANE"},
                    "enforcement": {"mode": "hard", "overridable": True},
                    "parameters": {"allowed_shift_codes": ["DAY_SHIFT_1", "DAY_SHIFT_3"]},
                },
                _scope_exclusivity_rule(
                    "FUNCTION_TEST_EXCLUSIVE",
                    {"effect_dimension_keys": ["function_test_dim"]},
                    mode="soft",
                    activation_mode="default_on",
                ),
            ],
        },
    )
    session.add(machine_type)
    await session.flush()
    machine = Machine(
        machine_type_id=machine_type.id,
        code="INTEGRATION-RULE-001",
        name="集成验证机台",
    )
    session.add(machine)
    await session.flush()

    function_template = StateFeatureDef(
        machine_type_id=machine_type.id,
        feature_key="function_test_dim",
        feature_name="功能调测状态维度",
        value_type="enum",
        allowed_values=["false", "true"],
        is_dimension_template=True,
    )
    session.add(function_template)
    await session.flush()
    feature_defs = [
        StateFeatureDef(
            machine_type_id=machine_type.id,
            feature_key="crane_lift_done",
            feature_name="吊装完成",
            value_type="enum",
            allowed_values=["false", "true"],
        ),
        StateFeatureDef(
            machine_type_id=machine_type.id,
            feature_key="functional_commissioning_done",
            feature_name="功能调测完成",
            value_type="enum",
            allowed_values=["false", "true"],
            dimension_template_id=function_template.id,
        ),
        StateFeatureDef(
            machine_type_id=machine_type.id,
            feature_key="mechanical_inspection_done",
            feature_name="机械检查完成",
            value_type="enum",
            allowed_values=["false", "true"],
        ),
    ]
    session.add_all(feature_defs)
    session.add_all([
        Resource(
            machine_id=machine.id,
            code="CRANE-01",
            name="一号行吊",
            resource_type="OVERHEAD_CRANE",
            capacity=1,
            is_available=True,
        ),
        Resource(
            machine_id=machine.id,
            code="CONTROL-01",
            name="控制调测组",
            resource_type="CONTROL_TEAM",
            capacity=1,
            is_available=True,
        ),
        Resource(
            machine_id=machine.id,
            code="MECH-01",
            name="机械检查组",
            resource_type="MECHANICAL_TEAM",
            capacity=1,
            is_available=True,
        ),
    ])

    current = MachineState(machine_id=machine.id, state_type="current", label="集成开始")
    target = MachineState(machine_id=machine.id, state_type="target", label="集成规则验证完成")
    session.add_all([current, target])
    await session.flush()
    for feature_key in (
        "crane_lift_done",
        "functional_commissioning_done",
        "mechanical_inspection_done",
    ):
        session.add_all([
            MachineStateFeature(
                machine_state_id=current.id,
                feature_key=feature_key,
                feature_value="false",
            ),
            MachineStateFeature(
                machine_state_id=target.id,
                feature_key=feature_key,
                feature_value="true",
            ),
        ])

    activities = [
        ("CRANE_LIFT", "吊装横梁", "STRUCTURE", "crane_lift_done", "OVERHEAD_CRANE", 30),
        (
            "FUNCTION_TEST",
            "功能联调",
            "CONTROL",
            "functional_commissioning_done",
            "CONTROL_TEAM",
            40,
        ),
        (
            "MECH_INSPECTION",
            "机械检查",
            "STRUCTURE",
            "mechanical_inspection_done",
            "MECHANICAL_TEAM",
            40,
        ),
    ]
    rule_ids: dict[str, int] = {}
    for code, name, subsystem, effect_key, resource_type, duration in activities:
        atomic = AtomicActivity(
            machine_type_id=machine_type.id,
            code=code,
            name=name,
            metadata_json={"responsible_subsystem": subsystem},
        )
        session.add(atomic)
        await session.flush()
        op_rule = OpRule(
            machine_type_id=machine_type.id,
            atomic_activity_id=atomic.id,
            code=f"RULE_{code}",
            name=name,
            duration_min=duration,
            is_active=True,
        )
        session.add(op_rule)
        await session.flush()
        rule_ids[code] = op_rule.id
        session.add_all([
            OpRuleEffect(op_rule_id=op_rule.id, feature_key=effect_key, new_value="true"),
            OpRuleResourceReq(
                op_rule_id=op_rule.id,
                resource_type=resource_type,
                quantity=1,
                is_required=True,
            ),
        ])
    await session.commit()
    return {
        "machine_type_id": machine_type.id,
        "machine_id": machine.id,
        "current_state_id": current.id,
        "target_state_id": target.id,
        **{f"{key.lower()}_rule_id": value for key, value in rule_ids.items()},
    }


async def _seed_cross_mode_continuity_scenario(session) -> dict[str, int]:
    machine_type = MachineType(
        code="CROSS_MODE_RULE_REALISTIC",
        name="跨求解模式责任连续性场景",
        scheduling_config={
            "responsible_subsystems": [
                {"code": "PROPULSION", "name": "推进子系统"},
                {"code": "CONTROL", "name": "控制子系统"},
            ],
            "rules": [
                {
                    "code": "SUBSYSTEM_CONTINUITY",
                    "name": "责任子系统连续性",
                    "type": "group_continuity",
                    "enabled": True,
                    "activation_mode": "optional",
                    "selector": {"match": "all"},
                    "enforcement": {"mode": "soft", "priority": 1, "overridable": False},
                    "parameters": {"group_by": "responsible_subsystem"},
                }
            ],
        },
    )
    session.add(machine_type)
    await session.flush()
    machine = Machine(
        machine_type_id=machine_type.id,
        code="CROSS-MODE-001",
        name="推进子系统连续性验证机台",
    )
    session.add(machine)
    await session.flush()
    session.add(
        Resource(
            machine_id=machine.id,
            code="INTEGRATION-TEAM-01",
            name="集成作业组",
            resource_type="INTEGRATION_TEAM",
            capacity=1,
            is_available=True,
        )
    )

    feature_keys = ["propulsion_mount_a", "control_check", "propulsion_mount_b"]
    for feature_key in feature_keys:
        session.add(
            StateFeatureDef(
                machine_type_id=machine_type.id,
                feature_key=feature_key,
                feature_name=feature_key,
                value_type="enum",
                allowed_values=["false", "true"],
            )
        )
    current = MachineState(machine_id=machine.id, state_type="current", label="连续性验证开始")
    target = MachineState(machine_id=machine.id, state_type="target", label="连续性验证完成")
    session.add_all([current, target])
    await session.flush()
    for feature_key in feature_keys:
        session.add_all([
            MachineStateFeature(
                machine_state_id=current.id,
                feature_key=feature_key,
                feature_value="false",
            ),
            MachineStateFeature(
                machine_state_id=target.id,
                feature_key=feature_key,
                feature_value="true",
            ),
        ])

    state_root = StateNode(
        machine_type_id=machine_type.id,
        level=1,
        code="CROSS_MODE_COMPLETE",
        name="跨模式验证完成",
        state_kind="aggregate",
    )
    activity_root = ActivityNode(
        machine_type_id=machine_type.id,
        level=1,
        code="CROSS_MODE_ACTIVITIES",
        name="跨模式验证活动",
    )
    session.add_all([state_root, activity_root])
    await session.flush()
    activity_package = ActivityNode(
        machine_type_id=machine_type.id,
        parent_id=activity_root.id,
        level=2,
        code="CROSS_MODE_PACKAGE",
        name="跨模式验证活动包",
    )
    session.add(activity_package)
    await session.flush()

    activity_specs = [
        ("PROP_A", "推进部件A安装", "PROPULSION", "propulsion_mount_a"),
        ("CONTROL_CHECK", "控制检查", "CONTROL", "control_check"),
        ("PROP_B", "推进部件B安装", "PROPULSION", "propulsion_mount_b"),
    ]
    for index, (code, name, subsystem, feature_key) in enumerate(activity_specs, start=1):
        session.add(
            StateNode(
                machine_type_id=machine_type.id,
                parent_id=state_root.id,
                level=2,
                code=f"STATE_{code}",
                name=f"{name}完成",
                feature_key=feature_key,
                operator="eq",
                target_value="true",
                state_kind="atomic",
                sort_order=index,
            )
        )
        atomic = AtomicActivity(
            machine_type_id=machine_type.id,
            code=code,
            name=name,
            sort_order=index,
            metadata_json={"responsible_subsystem": subsystem},
        )
        session.add(atomic)
        await session.flush()
        session.add(
            ActivityPackageAtomicRef(
                activity_node_id=activity_package.id,
                atomic_activity_id=atomic.id,
                sort_order=index,
            )
        )
        op_rule = OpRule(
            machine_type_id=machine_type.id,
            atomic_activity_id=atomic.id,
            code=f"RULE_{code}",
            name=name,
            duration_min=20,
            is_active=True,
        )
        session.add(op_rule)
        await session.flush()
        session.add_all([
            OpRuleEffect(op_rule_id=op_rule.id, feature_key=feature_key, new_value="true"),
            OpRuleResourceReq(
                op_rule_id=op_rule.id,
                resource_type="INTEGRATION_TEAM",
                quantity=1,
                is_required=True,
            ),
        ])

    intent = MaintenanceIntentTemplate(
        machine_type_id=machine_type.id,
        scope_activity_node_id=activity_root.id,
        issue_type="CROSS_MODE_RULE_ACCEPTANCE",
        name="跨模式排期规则验收",
        target_state_node_ids=[state_root.id],
        candidate_activity_scope_ids=[activity_root.id],
        observed_fact_templates=[],
        desired_fact_templates=[],
    )
    session.add(intent)
    await session.commit()
    return {
        "machine_id": machine.id,
        "current_state_id": current.id,
        "target_state_id": target.id,
        "state_root_id": state_root.id,
        "activity_root_id": activity_root.id,
        "intent_id": intent.id,
    }


def _overlaps(left: dict, right: dict) -> bool:
    return left["start_min"] < right["end_min"] and right["start_min"] < left["end_min"]


async def test_crane_exclusivity_function_test_soft_violation_and_exception_replan(
    client,
    db_session,
):
    ids = await _seed_crane_function_test_scenario(db_session)
    base_request = {
        "machine_id": ids["machine_id"],
        "current_state_id": ids["current_state_id"],
        "target_state_id": ids["target_state_id"],
        "objective": "minimize_makespan",
    }
    initial_response = await client.post("/api/v1/solve", json=base_request)
    assert initial_response.status_code == 200, initial_response.text
    initial = initial_response.json()
    assert initial["status"] == "done", initial
    tasks = {task["op_rule_code"]: task for task in initial["schedule"]["tasks"]}
    crane = tasks["RULE_CRANE_LIFT"]
    function_test = tasks["RULE_FUNCTION_TEST"]
    mechanical = tasks["RULE_MECH_INSPECTION"]
    assert not _overlaps(crane, function_test)
    assert not _overlaps(crane, mechanical)
    assert _overlaps(function_test, mechanical)
    assert initial["schedule"]["makespan"] == 70
    rule_diagnostics = initial["diagnostics"]["schedule"]["scheduling_rules"]
    assert set(rule_diagnostics["active_rule_codes"]) == {
        "CRANE_EXCLUSIVE",
        "CRANE_DAY_SHIFT_ONLY",
        "FUNCTION_TEST_EXCLUSIVE",
    }
    assert any(
        item["rule_code"] == "FUNCTION_TEST_EXCLUSIVE"
        and set(item["step_orders"]) == {function_test["step_order"], mechanical["step_order"]}
        for item in rule_diagnostics["violations"]
    )
    assert "function_test_dim" in function_test["effect_dimension_keys"]

    parent_plan_id = initial["candidate_plan_id"]
    exception_request = {
        **base_request,
        "parent_plan_id": parent_plan_id,
        "constraints": {
            "scheduling_rules": {
                "new_override": {
                    "rule_code": "CRANE_DAY_SHIFT_ONLY",
                    "source_step_id": crane["step_id"],
                    "parameters": {"allow_shift_codes": ["NIGHT_SHIFT_2"]},
                    "reason": "连续吊装作业需要跨入夜班",
                },
                "carry_parent_override_keys": [],
            }
        },
    }
    exception_response = await client.post("/api/v1/solve", json=exception_request)
    assert exception_response.status_code == 200, exception_response.text
    exception_plan = exception_response.json()
    assert exception_plan["status"] == "done", exception_plan
    child_plan = await db_session.get(CandidatePlan, exception_plan["candidate_plan_id"])
    await db_session.refresh(child_plan)
    assert child_plan.parent_plan_id == parent_plan_id
    assert child_plan.replan_reason == "scheduling_rule_exception"

    parent_request = await db_session.scalar(
        select(SolveRequest)
        .join(CandidatePlan, CandidatePlan.solve_request_id == SolveRequest.id)
        .where(CandidatePlan.id == parent_plan_id)
    )
    child_request = await db_session.scalar(
        select(SolveRequest)
        .join(CandidatePlan, CandidatePlan.solve_request_id == SolveRequest.id)
        .where(CandidatePlan.id == exception_plan["candidate_plan_id"])
    )
    assert parent_request.constraints["scheduling_rules"]["overrides"] == []
    child_overrides = child_request.constraints["scheduling_rules"]["overrides"]
    assert len(child_overrides) == 1
    assert child_overrides[0]["reason"] == "连续吊装作业需要跨入夜班"
    target_step = await db_session.get(CandidatePlanStep, child_overrides[0]["source_step_id"])
    assert target_step.candidate_plan_id == exception_plan["candidate_plan_id"]

    no_carry_response = await client.post(
        "/api/v1/solve",
        json={**base_request, "parent_plan_id": exception_plan["candidate_plan_id"]},
    )
    assert no_carry_response.status_code == 200
    assert no_carry_response.json()["status"] == "done"
    no_carry_request = await db_session.scalar(
        select(SolveRequest)
        .join(CandidatePlan, CandidatePlan.solve_request_id == SolveRequest.id)
        .where(CandidatePlan.id == no_carry_response.json()["candidate_plan_id"])
    )
    assert no_carry_request.constraints["scheduling_rules"]["overrides"] == []

    carry_response = await client.post(
        "/api/v1/solve",
        json={
            **base_request,
            "parent_plan_id": exception_plan["candidate_plan_id"],
            "constraints": {
                "scheduling_rules": {
                    "carry_parent_override_keys": [child_overrides[0]["override_key"]]
                }
            },
        },
    )
    assert carry_response.status_code == 200
    assert carry_response.json()["status"] == "done"
    carry_request = await db_session.scalar(
        select(SolveRequest)
        .join(CandidatePlan, CandidatePlan.solve_request_id == SolveRequest.id)
        .where(CandidatePlan.id == carry_response.json()["candidate_plan_id"])
    )
    assert len(carry_request.constraints["scheduling_rules"]["overrides"]) == 1

    missing_reason = await client.post(
        "/api/v1/solve",
        json={
            **base_request,
            "parent_plan_id": parent_plan_id,
            "constraints": {
                "scheduling_rules": {
                    "new_override": {
                        "rule_code": "CRANE_DAY_SHIFT_ONLY",
                        "source_step_id": crane["step_id"],
                        "parameters": {"allow_shift_codes": ["NIGHT_SHIFT_2"]},
                    }
                }
            },
        },
    )
    assert missing_reason.status_code == 422
    assert missing_reason.json()["error_message"]["error_code"] == "SCHEDULING_RULE_OVERRIDE_INVALID"


async def test_night_crane_wait_pulls_independent_later_work_forward_without_reordering_successor(
    client,
    db_session,
):
    ids = await _seed_crane_function_test_scenario(db_session)

    follower_feature = StateFeatureDef(
        machine_type_id=ids["machine_type_id"],
        feature_key="crane_follow_up_done",
        feature_name="Crane follow-up complete",
        value_type="enum",
        allowed_values=["false", "true"],
    )
    db_session.add(follower_feature)
    follower = AtomicActivity(
        machine_type_id=ids["machine_type_id"],
        code="CRANE_FOLLOW_UP",
        name="Crane follow-up alignment",
        sort_order=4,
        metadata_json={"responsible_subsystem": "STRUCTURE"},
    )
    db_session.add(follower)
    await db_session.flush()
    follower_rule = OpRule(
        machine_type_id=ids["machine_type_id"],
        atomic_activity_id=follower.id,
        code="RULE_CRANE_FOLLOW_UP",
        name="Crane follow-up alignment",
        duration_min=30,
        is_active=True,
    )
    db_session.add(follower_rule)
    await db_session.flush()
    db_session.add_all([
        MachineStateFeature(
            machine_state_id=ids["current_state_id"],
            feature_key="crane_follow_up_done",
            feature_value="false",
        ),
        MachineStateFeature(
            machine_state_id=ids["target_state_id"],
            feature_key="crane_follow_up_done",
            feature_value="true",
        ),
        Resource(
            machine_id=ids["machine_id"],
            code="FOLLOW-UP-01",
            name="Crane follow-up team",
            resource_type="FOLLOW_UP_TEAM",
            capacity=1,
            is_available=True,
        ),
        OpRulePrecond(
            op_rule_id=follower_rule.id,
            feature_key="crane_lift_done",
            operator="eq",
            feature_value="true",
        ),
        OpRuleEffect(
            op_rule_id=follower_rule.id,
            feature_key="crane_follow_up_done",
            new_value="true",
        ),
        OpRuleResourceReq(
            op_rule_id=follower_rule.id,
            resource_type="FOLLOW_UP_TEAM",
            quantity=1,
            is_required=True,
        ),
    ])

    weekly_windows = []
    for weekday in range(1, 8):
        weekly_windows.extend([
            {
                "weekday": weekday,
                "start_time": "08:00",
                "end_time": "20:00",
                "spans_next_day": False,
                "shift_code": "DAY_SHIFT_1",
                "shift_name": "Day shift",
            },
            {
                "weekday": weekday,
                "start_time": "20:00",
                "end_time": "08:00",
                "spans_next_day": True,
                "shift_code": "NIGHT_SHIFT_2",
                "shift_name": "Night shift",
            },
        ])
    calendar = WorkCalendar(
        code="CRANE_NIGHT_PULL_FORWARD",
        name="Crane night wait pull-forward acceptance",
    )
    db_session.add(calendar)
    await db_session.flush()
    revision = WorkCalendarRevision(
        work_calendar_id=calendar.id,
        revision_no=1,
        timezone="Asia/Shanghai",
        weekly_windows=weekly_windows,
        date_exceptions=[],
        checksum=definition_checksum("Asia/Shanghai", weekly_windows, []),
    )
    db_session.add(revision)
    await db_session.flush()
    calendar.current_revision_id = revision.id
    machine = await db_session.get(Machine, ids["machine_id"])
    machine.default_work_calendar_id = calendar.id
    await db_session.commit()

    response = await client.post(
        "/api/v1/solve",
        json={
            "machine_id": ids["machine_id"],
            "current_state_id": ids["current_state_id"],
            "target_state_id": ids["target_state_id"],
            "calendar_context": {
                "enabled": True,
                "schedule_start_at": "2026-07-13T20:00:00+08:00",
                "display_timezone": "Asia/Shanghai",
                "revision_policy": "latest",
            },
        },
    )
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "done", result
    tasks = {task["op_rule_code"]: task for task in result["schedule"]["tasks"]}
    crane = tasks["RULE_CRANE_LIFT"]
    independent_tasks = [tasks["RULE_FUNCTION_TEST"], tasks["RULE_MECH_INSPECTION"]]
    successor = tasks["RULE_CRANE_FOLLOW_UP"]

    assert crane["start_at"] == "2026-07-14T08:00:00+08:00"
    assert [segment["shift_code"] for segment in crane["segments"]] == ["DAY_SHIFT_1"]
    assert all(task["end_min"] <= crane["start_min"] for task in independent_tasks)
    assert all(
        task["segments"] and task["segments"][0]["shift_code"] == "NIGHT_SHIFT_2"
        for task in independent_tasks
    )
    assert any(task["step_order"] > crane["step_order"] for task in independent_tasks)

    assert crane["step_order"] in successor["predecessors"]
    assert successor["start_min"] >= crane["end_min"]
    assert all(task["calendar_pause_min"] == 0 for task in tasks.values())
    assert all(task["step_role"] == "normal" for task in tasks.values())
    active_rules = {
        rule["code"]: rule
        for rule in result["diagnostics"]["schedule"]["scheduling_rules"]["active_rules"]
    }
    assert active_rules["CRANE_EXCLUSIVE"]["presentation"] == {
        "gantt_marker": {"text": "吊", "color": "#f59e0b"}
    }


async def test_failed_crane_shift_plan_becomes_contiguous_only_after_explicit_exception(
    client,
    db_session,
):
    ids = await _seed_crane_function_test_scenario(db_session)
    crane_rule = await db_session.get(OpRule, ids["crane_lift_rule_id"])
    crane_rule.duration_min = 600
    weekly_windows = []
    for weekday in range(1, 8):
        weekly_windows.extend([
            {
                "weekday": weekday,
                "start_time": "08:00",
                "end_time": "12:00",
                "spans_next_day": False,
                "shift_code": "DAY_SHIFT_1",
                "shift_name": "白班一",
            },
            {
                "weekday": weekday,
                "start_time": "12:00",
                "end_time": "16:00",
                "spans_next_day": False,
                "shift_code": "NIGHT_SHIFT_2",
                "shift_name": "夜班二",
            },
            {
                "weekday": weekday,
                "start_time": "16:00",
                "end_time": "20:00",
                "spans_next_day": False,
                "shift_code": "DAY_SHIFT_3",
                "shift_name": "白班三",
            },
        ])
    calendar = WorkCalendar(code="THREE_SHIFT_RULE_TEST", name="三班连续性验收日历")
    db_session.add(calendar)
    await db_session.flush()
    revision = WorkCalendarRevision(
        work_calendar_id=calendar.id,
        revision_no=1,
        timezone="Asia/Shanghai",
        weekly_windows=weekly_windows,
        date_exceptions=[],
        checksum=definition_checksum("Asia/Shanghai", weekly_windows, []),
    )
    db_session.add(revision)
    await db_session.flush()
    calendar.current_revision_id = revision.id
    machine = await db_session.get(Machine, ids["machine_id"])
    machine.default_work_calendar_id = calendar.id
    await db_session.commit()

    base_request = {
        "machine_id": ids["machine_id"],
        "current_state_id": ids["current_state_id"],
        "target_state_id": ids["target_state_id"],
        "calendar_context": {
            "enabled": True,
            "schedule_start_at": "2026-07-13T08:00:00+08:00",
            "display_timezone": "Asia/Shanghai",
            "revision_policy": "latest",
        },
    }
    failed_response = await client.post("/api/v1/solve", json=base_request)
    assert failed_response.status_code == 200, failed_response.text
    failed = failed_response.json()
    assert failed["status"] == "failed", failed
    assert failed["error_code"] == "CALENDAR_CONTIGUOUS_WINDOW_TOO_SHORT"
    crane_candidate = next(
        item for item in failed["exception_candidates"]
        if item["op_rule_code"] == "RULE_CRANE_LIFT"
    )
    assert "CRANE_DAY_SHIFT_ONLY" in crane_candidate["matched_scheduling_rules"]

    exception_response = await client.post(
        "/api/v1/solve",
        json={
            **base_request,
            "parent_plan_id": failed["candidate_plan_id"],
            "constraints": {
                "scheduling_rules": {
                    "new_override": {
                        "rule_code": "CRANE_DAY_SHIFT_ONLY",
                        "source_step_id": crane_candidate["step_id"],
                        "parameters": {"allow_shift_codes": ["NIGHT_SHIFT_2"]},
                        "reason": "本次吊装必须在连续班次内完成",
                    },
                    "carry_parent_override_keys": [],
                }
            },
        },
    )
    assert exception_response.status_code == 200, exception_response.text
    replanned = exception_response.json()
    assert replanned["status"] == "done", replanned
    crane_task = next(
        task for task in replanned["schedule"]["tasks"]
        if task["op_rule_code"] == "RULE_CRANE_LIFT"
    )
    assert crane_task["elapsed_min"] == crane_task["duration_min"] == 600
    assert crane_task["calendar_pause_min"] == 0
    assert [segment["shift_code"] for segment in crane_task["segments"]] == [
        "DAY_SHIFT_1",
        "NIGHT_SHIFT_2",
        "DAY_SHIFT_3",
    ]


async def test_subsystem_continuity_is_consistent_across_snapshot_layered_and_maintenance(
    client,
    db_session,
):
    ids = await _seed_cross_mode_continuity_scenario(db_session)
    constraints = {
        "scheduling_rules": {"active_rule_codes": ["SUBSYSTEM_CONTINUITY"]}
    }
    snapshot_response = await client.post(
        "/api/v1/solve",
        json={
            "machine_id": ids["machine_id"],
            "current_state_id": ids["current_state_id"],
            "target_state_id": ids["target_state_id"],
            "constraints": constraints,
        },
    )
    assert snapshot_response.status_code == 200, snapshot_response.text
    snapshot = snapshot_response.json()
    assert snapshot["status"] == "done", snapshot

    layered = await solve_layered(
        LayeredSolveRequest(
            machine_id=ids["machine_id"],
            current_state_id=ids["current_state_id"],
            target_state_node_ids=[ids["state_root_id"]],
            activity_scope_node_ids=[ids["activity_root_id"]],
            constraints=constraints,
        ),
        db_session,
    )
    assert layered["status"] == "done", layered
    maintenance = await solve_maintenance(
        MaintenanceSolveRequest(
            machine_id=ids["machine_id"],
            current_state_id=ids["current_state_id"],
            intent_template_ids=[ids["intent_id"]],
            constraints=constraints,
        ),
        db_session,
    )
    assert maintenance["status"] == "done", maintenance

    results = [
        (snapshot["schedule"]["tasks"], snapshot["diagnostics"]["schedule"]),
        (layered["schedule"]["tasks"], layered["diagnostics"]["schedule"]),
        (maintenance["schedule"]["tasks"], maintenance["diagnostics"]["schedule"]),
    ]
    for tasks, diagnostics in results:
        scheduling_rules = diagnostics["scheduling_rules"]
        assert scheduling_rules["active_rule_codes"] == ["SUBSYSTEM_CONTINUITY"]
        propulsion = next(
            group for group in scheduling_rules["continuity_groups"]
            if group["group_key"] == "SUBSYSTEM_CONTINUITY:PROPULSION"
        )
        assert propulsion["internal_gap_min"] == 0
        assert propulsion["interruption_count"] == 0
        assert propulsion["span_min"] == 40
        assert sum(task["responsible_subsystem"] == "PROPULSION" for task in tasks) == 2
        assert all("SUBSYSTEM_CONTINUITY" in task["matched_scheduling_rules"] for task in tasks)
