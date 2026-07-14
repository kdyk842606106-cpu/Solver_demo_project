"""Compare MI-HP-001 solve quality across integration-rule combinations."""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from sqlalchemy import select


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import ActivityNode, Machine, MachineState, MachineType, StateNode, WorkCalendar
from app.db.schemas import LayeredSolveRequest
from app.db.session import AsyncSessionLocal, async_engine
from app.services.layered_solve import solve_layered
from app.services.scheduling_rule_config import validate_machine_type_scheduling_rules


FUNCTION_TEST_DIMENSION = "mi_hp_function_test_dim"
REQUIRED_RULES = {"CRANE_EXCLUSIVE", "CRANE_DAY_SHIFT_ONLY"}
SCENARIOS = {
    "required_only": [],
    "subsystem_continuity": ["SUBSYSTEM_CONTINUITY"],
    "function_test_exclusive": ["FUNCTION_TEST_EXCLUSIVE"],
    "all_rules": ["SUBSYSTEM_CONTINUITY", "FUNCTION_TEST_EXCLUSIVE"],
}

MAX_FUNCTION_ONLY_MAKESPAN_OVERHEAD = 0.05
MAX_ALL_RULES_MAKESPAN_OVERHEAD = 0.15


def _overlaps(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return left["start_min"] < right["end_min"] and right["start_min"] < left["end_min"]


def _maximum_concurrency(tasks: list[dict[str, Any]]) -> int:
    events = [
        event
        for task in tasks
        for event in ((task["start_min"], 1), (task["end_min"], -1))
    ]
    active = maximum = 0
    for _, delta in sorted(events, key=lambda item: (item[0], item[1])):
        active += delta
        maximum = max(maximum, active)
    return maximum


def _subsystem_quality(tasks: list[dict[str, Any]]) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        subsystem = task.get("responsible_subsystem")
        if subsystem:
            groups[str(subsystem)].append(task)
    details: dict[str, Any] = {}
    total_span = total_gap = total_interruptions = 0
    for subsystem, group_tasks in sorted(groups.items()):
        if len(group_tasks) < 2:
            continue
        start = min(task["start_min"] for task in group_tasks)
        end = max(task["end_min"] for task in group_tasks)
        duration = sum(task["duration_min"] for task in group_tasks)
        group_orders = {task["step_order"] for task in group_tasks}
        interruptions = [
            task["step_order"]
            for task in tasks
            if task["step_order"] not in group_orders
            and task["start_min"] >= start
            and task["end_min"] <= end
        ]
        span = end - start
        gap = max(0, span - duration)
        details[subsystem] = {
            "task_count": len(group_tasks),
            "span_min": span,
            "internal_gap_min": gap,
            "interruption_count": len(interruptions),
        }
        total_span += span
        total_gap += gap
        total_interruptions += len(interruptions)
    return {
        "total_span_min": total_span,
        "total_internal_gap_min": total_gap,
        "total_interruption_count": total_interruptions,
        "groups": details,
    }


def summarize_quality(result: dict[str, Any]) -> dict[str, Any]:
    tasks = result["schedule"]["tasks"]
    pairs = [
        (left, right)
        for index, left in enumerate(tasks)
        for right in tasks[index + 1:]
        if _overlaps(left, right)
    ]
    crane_tasks = [
        task for task in tasks
        if any(
            req.get("resource_type") == "OVERHEAD_CRANE"
            for req in task.get("resource_reqs") or []
        )
    ]
    function_tasks = [
        task for task in tasks
        if FUNCTION_TEST_DIMENSION in (task.get("effect_dimension_keys") or [])
    ]
    crane_orders = {task["step_order"] for task in crane_tasks}
    function_orders = {task["step_order"] for task in function_tasks}
    crane_overlap_pairs = [
        [left["step_order"], right["step_order"]]
        for left, right in pairs
        if left["step_order"] in crane_orders or right["step_order"] in crane_orders
    ]
    function_overlap_pairs = [
        [left["step_order"], right["step_order"]]
        for left, right in pairs
        if left["step_order"] in function_orders or right["step_order"] in function_orders
    ]
    rule_diagnostics = result["diagnostics"]["schedule"]["scheduling_rules"]
    marker_rules = {
        rule["code"]: rule["presentation"]["gantt_marker"]
        for rule in rule_diagnostics.get("active_rules") or []
        if (rule.get("presentation") or {}).get("gantt_marker")
    }
    marker_task_codes = sorted(
        task["op_rule_code"]
        for task in tasks
        if set(task.get("matched_scheduling_rules") or []).intersection(marker_rules)
    )
    total_duration = sum(task["duration_min"] for task in tasks)
    makespan = result["schedule"]["makespan"]
    return {
        "candidate_plan_id": result["candidate_plan_id"],
        "task_count": len(tasks),
        "makespan_min": makespan,
        "total_activity_duration_min": total_duration,
        "schedule_density": round(total_duration / makespan, 3) if makespan else None,
        "parallel_pair_count": len(pairs),
        "maximum_concurrency": _maximum_concurrency(tasks),
        "active_rule_codes": rule_diagnostics["active_rule_codes"],
        "soft_rule_violation_count": len(rule_diagnostics["violations"]),
        "crane_task_count": len(crane_tasks),
        "crane_task_codes": sorted(task["op_rule_code"] for task in crane_tasks),
        "gantt_marker_rules": marker_rules,
        "gantt_marker_task_codes": marker_task_codes,
        "crane_overlap_pair_count": len(crane_overlap_pairs),
        "crane_overlap_pairs": crane_overlap_pairs,
        "crane_shift_codes": sorted({
            segment.get("shift_code")
            for task in crane_tasks
            for segment in task.get("segments") or []
            if segment.get("shift_code")
        }),
        "function_test_task_count": len(function_tasks),
        "function_test_overlap_pair_count": len(function_overlap_pairs),
        "function_test_overlap_pairs": function_overlap_pairs,
        "calendar_pause_min": sum(task.get("calendar_pause_min") or 0 for task in tasks),
        "subsystem_quality": _subsystem_quality(tasks),
    }


def assert_quality_gates(summaries: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Fail the acceptance run when rule quality materially regresses."""
    required = summaries["required_only"]
    continuity = summaries["subsystem_continuity"]
    function_only = summaries["function_test_exclusive"]
    all_rules = summaries["all_rules"]
    baseline_makespan = required["makespan_min"]

    function_overhead = (
        function_only["makespan_min"] - baseline_makespan
    ) / baseline_makespan
    all_rules_overhead = (
        all_rules["makespan_min"] - baseline_makespan
    ) / baseline_makespan

    checks = {
        "function_test_exclusive_has_zero_overlap": (
            function_only["function_test_overlap_pair_count"] == 0
        ),
        "all_rules_have_zero_function_test_overlap": (
            all_rules["function_test_overlap_pair_count"] == 0
        ),
        "subsystem_continuity_has_zero_internal_gap": (
            continuity["subsystem_quality"]["total_internal_gap_min"] == 0
        ),
        "all_rules_have_zero_subsystem_internal_gap": (
            all_rules["subsystem_quality"]["total_internal_gap_min"] == 0
        ),
        "subsystem_continuity_reduces_interruptions": (
            continuity["subsystem_quality"]["total_interruption_count"]
            <= required["subsystem_quality"]["total_interruption_count"]
        ),
        "all_rules_reduce_subsystem_interruptions": (
            all_rules["subsystem_quality"]["total_interruption_count"]
            <= required["subsystem_quality"]["total_interruption_count"]
        ),
        "function_test_makespan_overhead_within_limit": (
            function_overhead <= MAX_FUNCTION_ONLY_MAKESPAN_OVERHEAD
        ),
        "all_rules_makespan_overhead_within_limit": (
            all_rules_overhead <= MAX_ALL_RULES_MAKESPAN_OVERHEAD
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"MI-HP-001 quality gates failed: {failed}")
    return {
        "status": "passed",
        "checks": checks,
        "function_test_makespan_overhead_pct": round(function_overhead * 100, 1),
        "all_rules_makespan_overhead_pct": round(all_rules_overhead * 100, 1),
        "limits": {
            "function_test_makespan_overhead_pct": (
                MAX_FUNCTION_ONLY_MAKESPAN_OVERHEAD * 100
            ),
            "all_rules_makespan_overhead_pct": MAX_ALL_RULES_MAKESPAN_OVERHEAD * 100,
        },
    }


async def run_quality_matrix(session) -> dict[str, Any]:
    machine = await session.scalar(
        select(Machine)
        .join(MachineType, MachineType.id == Machine.machine_type_id)
        .where(
            Machine.code == "MI-HP-001",
            MachineType.code == "MECH_INTEGRATION_HIGH_PARALLEL",
        )
    )
    if machine is None:
        raise RuntimeError(
            "MI-HP-001 is missing; load seeds/011_mechanical_integration_high_parallel_seed.sql first"
        )
    current_state = await session.scalar(
        select(MachineState).where(
            MachineState.machine_id == machine.id,
            MachineState.state_type == "current",
        )
    )
    target_root = await session.scalar(
        select(StateNode).where(
            StateNode.machine_type_id == machine.machine_type_id,
            StateNode.code == "MI_HP_COMPLETE",
        )
    )
    activity_root = await session.scalar(
        select(ActivityNode).where(
            ActivityNode.machine_type_id == machine.machine_type_id,
            ActivityNode.code == "MI_HP_ACT",
        )
    )
    default_calendar = await session.scalar(
        select(WorkCalendar).where(
            WorkCalendar.is_system_default.is_(True),
            WorkCalendar.is_active.is_(True),
        )
    )
    if current_state is None or target_root is None or activity_root is None:
        raise RuntimeError("MI-HP-001 layered solve data is incomplete")
    if default_calendar is None:
        raise RuntimeError("System default work calendar is required for shift-rule validation")

    modeling_issues, solver_ready_issues = await validate_machine_type_scheduling_rules(
        machine.machine_type_id,
        session,
    )
    if solver_ready_issues:
        raise RuntimeError(f"MI-HP-001 scheduling configuration is blocked: {solver_ready_issues}")
    if modeling_issues:
        raise RuntimeError(f"MI-HP-001 scheduling configuration has warnings: {modeling_issues}")

    summaries: dict[str, Any] = {}
    for scenario_name, optional_rule_codes in SCENARIOS.items():
        result = await solve_layered(
            LayeredSolveRequest(
                machine_id=machine.id,
                current_state_id=current_state.id,
                target_state_node_ids=[target_root.id],
                activity_scope_node_ids=[activity_root.id],
                constraints={
                    "scheduling_rules": {
                        "active_rule_codes": optional_rule_codes,
                    }
                },
                objectives=[{"type": "minimize_makespan", "weight": 1.0}],
                calendar_context={
                    "enabled": True,
                    "schedule_start_at": "2026-07-13T18:00:00+08:00",
                    "display_timezone": "Asia/Shanghai",
                    "revision_policy": "latest",
                },
            ),
            session,
        )
        if result.get("status") != "done":
            raise RuntimeError(f"Scenario {scenario_name} failed: {result}")
        summary = summarize_quality(result)
        if not REQUIRED_RULES.issubset(summary["active_rule_codes"]):
            raise RuntimeError(f"Scenario {scenario_name} did not enforce required crane rules")
        if summary["crane_overlap_pair_count"] != 0:
            raise RuntimeError(f"Scenario {scenario_name} allowed crane overlap: {summary}")
        if summary["crane_shift_codes"] != ["DAY_SHIFT"]:
            raise RuntimeError(f"Scenario {scenario_name} used a forbidden crane shift: {summary}")
        if summary["calendar_pause_min"] != 0:
            raise RuntimeError(f"Scenario {scenario_name} paused an activity: {summary}")
        if summary["gantt_marker_rules"].get("CRANE_EXCLUSIVE") != {
            "text": "吊",
            "color": "#f59e0b",
        }:
            raise RuntimeError(f"Scenario {scenario_name} lost the crane Gantt marker: {summary}")
        if summary["gantt_marker_task_codes"] != summary["crane_task_codes"]:
            raise RuntimeError(f"Scenario {scenario_name} marked non-crane tasks: {summary}")
        summaries[scenario_name] = summary

    quality_gates = assert_quality_gates(summaries)
    return {
        "machine_code": machine.code,
        "calendar_code": default_calendar.code,
        "validation_warning_codes": [item["code"] for item in modeling_issues],
        "quality_gates": quality_gates,
        "scenarios": summaries,
    }


async def main() -> None:
    try:
        async with AsyncSessionLocal() as session:
            report = await run_quality_matrix(session)
            print(json.dumps(report, ensure_ascii=False, indent=2))
    finally:
        await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
