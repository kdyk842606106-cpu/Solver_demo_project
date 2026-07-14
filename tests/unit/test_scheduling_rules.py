from ortools.sat.python import cp_model
import pytest

from app.core.scheduler.loader import RagData, StepData
from app.core.scheduler.model import build_model
from app.core.scheduler.rules import (
    SchedulingRuleContext,
    SchedulingRuleError,
    builtin_scheduling_rules,
    scheduling_rule_type_descriptors,
    validate_scheduling_config,
)
from app.db.models import Machine, MachineType
from app.services.scheduling_rule_requests import prepare_scheduling_rule_constraints


def _rule(rule_type: str, **overrides):
    payload = {
        "code": f"TEST_{rule_type.upper()}",
        "name": "test",
        "type": rule_type,
        "enabled": True,
        "activation_mode": "default_on",
        "selector": {"match": "all"},
        "enforcement": {"mode": "soft", "overridable": False},
        "parameters": {},
    }
    payload.update(overrides)
    return payload


def test_registered_rule_types_are_read_only_descriptors():
    descriptors = scheduling_rule_type_descriptors()
    assert {item["type"] for item in descriptors} == {
        "group_continuity",
        "scope_exclusivity",
        "state_package_continuity",
        "shift_restriction",
    }
    assert all("compiler" not in item for item in descriptors)
    state_package = next(
        item for item in descriptors if item["type"] == "state_package_continuity"
    )
    assert state_package["supported_modes"] == ["layered", "maintenance"]
    assert state_package["builtin_rule"]["code"] == "STATE_PACKAGE_CONTINUITY"
    assert builtin_scheduling_rules("snapshot") == []
    assert builtin_scheduling_rules("layered")[0]["code"] == "STATE_PACKAGE_CONTINUITY"


def test_unknown_type_and_disabled_required_rule_are_rejected():
    with pytest.raises(SchedulingRuleError) as unknown:
        validate_scheduling_config({"rules": [_rule("unknown")]})
    assert unknown.value.code == "SCHEDULING_RULE_UNKNOWN_TYPE"

    required = _rule("scope_exclusivity", enabled=False, activation_mode="required")
    with pytest.raises(SchedulingRuleError) as disabled:
        validate_scheduling_config({"rules": [required]})
    assert disabled.value.code == "SCHEDULING_RULE_CONFIG_INVALID"


def test_shift_restriction_requires_nonempty_shift_codes():
    invalid = _rule(
        "shift_restriction",
        parameters={"allowed_shift_codes": []},
    )
    with pytest.raises(SchedulingRuleError) as error:
        validate_scheduling_config({"rules": [invalid]})
    assert error.value.code == "SCHEDULING_RULE_CONFIG_INVALID"


def test_gantt_marker_presentation_is_normalized_and_validated():
    normalized = validate_scheduling_config({
        "rules": [
            _rule(
                "scope_exclusivity",
                presentation={"gantt_marker": {"text": " 吊 ", "color": "#F59E0B"}},
            )
        ]
    })
    assert normalized["rules"][0]["presentation"] == {
        "gantt_marker": {"text": "吊", "color": "#f59e0b"}
    }

    default_color = validate_scheduling_config({
        "rules": [
            _rule(
                "scope_exclusivity",
                presentation={"gantt_marker": {"text": "吊"}},
            )
        ]
    })
    assert default_color["rules"][0]["presentation"]["gantt_marker"]["color"] == "#f59e0b"

    for marker in (
        {"text": ""},
        {"text": "标识文字过长"},
        {"text": "吊", "color": "orange"},
    ):
        with pytest.raises(SchedulingRuleError) as error:
            validate_scheduling_config({
                "rules": [
                    _rule(
                        "scope_exclusivity",
                        presentation={"gantt_marker": marker},
                    )
                ]
            })
        assert error.value.code == "SCHEDULING_RULE_CONFIG_INVALID"


def test_hard_scope_exclusivity_lets_scheduler_choose_order():
    rag = RagData(
        candidate_plan_id=1,
        steps=[
            StepData(1, 1, "CRANE", "Crane", 60),
            StepData(2, 2, "OTHER", "Other", 60),
        ],
        edges=[],
    )
    context = SchedulingRuleContext(hard_exclusive_pairs={(1, 2)})
    schedule_model = build_model(rag, [], scheduling_rule_context=context)
    solver = cp_model.CpSolver()
    assert solver.solve(schedule_model.model) == cp_model.OPTIMAL
    left = schedule_model.task_vars[1]
    right = schedule_model.task_vars[2]
    assert solver.value(left.end) <= solver.value(right.start) or solver.value(right.end) <= solver.value(left.start)
    assert solver.value(schedule_model.makespan) == 120


def test_soft_scope_exclusivity_is_combined_with_objective():
    rule = _rule("scope_exclusivity")
    context = SchedulingRuleContext(
        active_rules=[rule],
        soft_exclusive_rules=[{"rule": rule, "pairs": [(1, 2)]}],
    )
    rag = RagData(
        candidate_plan_id=1,
        steps=[StepData(1, 1, "A", "A", 60), StepData(2, 2, "B", "B", 60)],
        edges=[],
    )
    schedule_model = build_model(rag, [], scheduling_rule_context=context)
    assert schedule_model.objective_cache["scheduling_rule_terms"][0]["rule_code"] == rule["code"]


@pytest.mark.asyncio
async def test_initial_solve_cannot_carry_rule_exception(db_session):
    with pytest.raises(SchedulingRuleError) as error:
        await prepare_scheduling_rule_constraints(
            machine_id=999,
            parent_plan_id=None,
            constraints={
                "scheduling_rules": {
                    "new_override": {
                        "rule_code": "CRANE_DAY_SHIFT_ONLY",
                        "source_step_id": 1,
                        "reason": "not allowed on initial solve",
                    }
                }
            },
            session=db_session,
        )
    assert error.value.code == "SCHEDULING_RULE_OVERRIDE_INITIAL_SOLVE_FORBIDDEN"


@pytest.mark.asyncio
async def test_required_rule_is_automatic_and_optional_rules_are_independent(db_session):
    machine_type = MachineType(
        code="RULE_UNIT_MT",
        name="Rule unit type",
        scheduling_config={
            "responsible_subsystems": [],
            "rules": [
                _rule(
                    "scope_exclusivity",
                    code="REQUIRED_EXCLUSIVE",
                    activation_mode="required",
                    enforcement={"mode": "hard", "overridable": False},
                    presentation={"gantt_marker": {"text": "吊", "color": "#f59e0b"}},
                ),
                _rule("group_continuity", code="OPTIONAL_CONTINUITY", activation_mode="optional"),
            ],
        },
    )
    db_session.add(machine_type)
    await db_session.flush()
    machine = Machine(machine_type_id=machine_type.id, code="RULE_UNIT_M", name="Rule unit machine")
    db_session.add(machine)
    await db_session.flush()

    only_required = await prepare_scheduling_rule_constraints(
        machine_id=machine.id,
        parent_plan_id=None,
        constraints={"scheduling_rules": {"active_rule_codes": []}},
        session=db_session,
    )
    assert only_required["scheduling_rules"]["active_rule_codes"] == ["REQUIRED_EXCLUSIVE"]
    assert only_required["scheduling_rules"]["snapshot"][0]["presentation"] == {
        "gantt_marker": {"text": "吊", "color": "#f59e0b"}
    }

    with_optional = await prepare_scheduling_rule_constraints(
        machine_id=machine.id,
        parent_plan_id=None,
        constraints={"scheduling_rules": {"active_rule_codes": ["OPTIONAL_CONTINUITY"]}},
        session=db_session,
    )
    assert with_optional["scheduling_rules"]["active_rule_codes"] == [
        "OPTIONAL_CONTINUITY",
        "REQUIRED_EXCLUSIVE",
    ]


@pytest.mark.asyncio
async def test_state_package_continuity_builtin_is_mode_scoped(db_session):
    machine_type = MachineType(
        code="STATE_PACKAGE_RULE_MT",
        name="State package rule type",
        scheduling_config={"responsible_subsystems": [], "rules": []},
    )
    db_session.add(machine_type)
    await db_session.flush()
    machine = Machine(
        machine_type_id=machine_type.id,
        code="STATE_PACKAGE_RULE_M",
        name="State package rule machine",
    )
    db_session.add(machine)
    await db_session.flush()

    layered = await prepare_scheduling_rule_constraints(
        machine_id=machine.id,
        parent_plan_id=None,
        constraints={
            "scheduling_rules": {
                "active_rule_codes": ["STATE_PACKAGE_CONTINUITY"],
            }
        },
        session=db_session,
        solve_mode="layered",
    )
    assert layered["scheduling_rules"]["active_rule_codes"] == [
        "STATE_PACKAGE_CONTINUITY"
    ]
    assert layered["scheduling_rules"]["snapshot"][0]["type"] == (
        "state_package_continuity"
    )

    with pytest.raises(SchedulingRuleError) as error:
        await prepare_scheduling_rule_constraints(
            machine_id=machine.id,
            parent_plan_id=None,
            constraints={
                "scheduling_rules": {
                    "active_rule_codes": ["STATE_PACKAGE_CONTINUITY"],
                }
            },
            session=db_session,
            solve_mode="snapshot",
        )
    assert error.value.code == "SCHEDULING_RULE_CONFIG_INVALID"
