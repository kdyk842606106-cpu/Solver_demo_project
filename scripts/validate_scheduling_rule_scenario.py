"""Run the persisted mechanical-integration scheduling-rule acceptance scenario."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import select


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db.models import ActivityNode, Machine, MachineState, MachineType, StateNode
from app.db.schemas import LayeredSolveRequest
from app.db.session import AsyncSessionLocal, async_engine
from app.services.layered_solve import solve_layered
from app.services.scheduling_rule_config import validate_machine_type_scheduling_rules


async def main() -> None:
    async with AsyncSessionLocal() as session:
        machine = await session.scalar(
            select(Machine)
            .join(MachineType, MachineType.id == Machine.machine_type_id)
            .where(
                Machine.code == "MI-CONT-001",
                MachineType.code == "MECH_INTEGRATION_CONTINUITY",
            )
        )
        if machine is None:
            raise RuntimeError(
                "MECH_INTEGRATION_CONTINUITY seed is missing; load "
                "seeds/010_mechanical_integration_state_continuity_seed.sql first"
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
                StateNode.code == "MECH_INTEGRATION_COMPLETE",
            )
        )
        activity_root = await session.scalar(
            select(ActivityNode).where(
                ActivityNode.machine_type_id == machine.machine_type_id,
                ActivityNode.code == "MECH_INTEGRATION_ACT",
            )
        )
        if current_state is None or target_root is None or activity_root is None:
            raise RuntimeError("Mechanical integration acceptance seed is incomplete")

        modeling_issues, solver_ready_issues = await validate_machine_type_scheduling_rules(
            machine.machine_type_id,
            session,
        )
        if solver_ready_issues:
            raise RuntimeError(f"Scheduling rule validation is blocked: {solver_ready_issues}")

        result = await solve_layered(
            LayeredSolveRequest(
                machine_id=machine.id,
                current_state_id=current_state.id,
                target_state_node_ids=[target_root.id],
                activity_scope_node_ids=[activity_root.id],
                constraints={
                    "scheduling_rules": {
                        "active_rule_codes": ["SUBSYSTEM_CONTINUITY"]
                    }
                },
                objectives=[{"type": "minimize_makespan", "weight": 1.0}],
            ),
            session,
        )
        if result.get("status") != "done":
            raise RuntimeError(f"Acceptance solve failed: {result}")

        scheduling_rules = result["diagnostics"]["schedule"]["scheduling_rules"]
        groups = {
            item["group_key"]: item
            for item in scheduling_rules["continuity_groups"]
        }
        expected_groups = {
            "SUBSYSTEM_CONTINUITY:STRUCTURE",
            "SUBSYSTEM_CONTINUITY:TRANSFER",
        }
        if not expected_groups.issubset(groups):
            raise RuntimeError(f"Missing continuity groups: {expected_groups - set(groups)}")
        for group_key in expected_groups:
            group = groups[group_key]
            if group["internal_gap_min"] != 0 or group["interruption_count"] != 0:
                raise RuntimeError(f"Continuity group is not compact: {group}")

        tasks = result["schedule"]["tasks"]
        summary = {
            "status": result["status"],
            "candidate_plan_id": result["candidate_plan_id"],
            "machine_code": machine.code,
            "makespan_min": result["schedule"]["makespan"],
            "active_rule_codes": scheduling_rules["active_rule_codes"],
            "responsible_subsystems": sorted({
                task["responsible_subsystem"] for task in tasks
            }),
            "continuity_groups": {
                key: {
                    "span_min": groups[key]["span_min"],
                    "internal_gap_min": groups[key]["internal_gap_min"],
                    "interruption_count": groups[key]["interruption_count"],
                }
                for key in sorted(expected_groups)
            },
            "validation_warning_codes": [item["code"] for item in modeling_issues],
        }
        print(json.dumps(summary, ensure_ascii=False, indent=2))

    await async_engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
