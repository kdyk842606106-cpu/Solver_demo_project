"""Debug Scheduler/Planner failures against the current database.

Examples:
  python scripts/debug_solve_diagnostics.py --solve-request-id 123
  python scripts/debug_solve_diagnostics.py --candidate-plan-id 456
  python scripts/debug_solve_diagnostics.py --machine-id 10 --current-state-id 20 --target-state-id 21
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import desc, select

from app.core.planner.search import build_rag, save_candidate_plan
from app.core.scheduler.diagnostics import diagnose_schedule_inputs, topological_blockers
from app.core.scheduler.loader import load_rag, load_resources
from app.core.scheduler.model import step_resource_requirements
from app.core.scheduler.solver import solve_schedule
from app.db.models import CandidatePlan, MachineState, SolveRequest
from app.db.session import AsyncSessionLocal


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, default=str)


def _print_section(title: str, data: Any) -> None:
    print(f"\n=== {title} ===")
    print(_json(data))


async def _latest_plan_for_request(session, solve_request_id: int) -> int | None:
    result = await session.execute(
        select(CandidatePlan.id)
        .where(CandidatePlan.solve_request_id == solve_request_id)
        .order_by(desc(CandidatePlan.id))
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _diagnose_existing_plan(session, candidate_plan_id: int) -> None:
    rag = await load_rag(candidate_plan_id, session)
    if rag is None:
        print(f"Candidate plan {candidate_plan_id} not found or has no steps.")
        return

    resource_types = sorted({
        resource_type
        for step in rag.steps
        for resource_type in step_resource_requirements(step)
    })
    resources = await load_resources(resource_types, session)

    diagnostics = diagnose_schedule_inputs(rag, resources)
    topology = topological_blockers(rag)
    schedule = await solve_schedule(candidate_plan_id, session)

    _print_section("RAG Summary", {
        "candidate_plan_id": candidate_plan_id,
        "step_count": len(rag.steps),
        "edge_count": len(rag.edges),
        "resource_types": resource_types,
        "first_steps": [
            {
                "step_order": step.step_order,
                "op_rule_id": step.op_rule_id,
                "op_rule_code": step.op_rule_code,
                "duration_min": step.duration_min,
                "resource_reqs": step.resource_reqs,
                "not_before": step.not_before,
            }
            for step in rag.steps[:20]
        ],
    })
    _print_section("Schedule Input Diagnostics", diagnostics)
    _print_section("Topological Diagnostics", topology)
    _print_section("Solver Result", {
        "status": schedule.status,
        "error_message": schedule.error_message,
        "makespan": schedule.makespan,
        "solver_stats": schedule.solver_stats,
        "diagnostics": schedule.diagnostics,
    })


async def _create_debug_plan(session, machine_id: int, current_state_id: int, target_state_id: int) -> int | None:
    plan = await build_rag(current_state_id, target_state_id, session)
    _print_section("Planner Result", {
        "status": plan.status,
        "error_message": plan.error_message,
        "diagnostics": plan.diagnostics,
        "rag_nodes": len(plan.rag.nodes) if plan.rag else None,
        "rag_edges": len(plan.rag.edges) if plan.rag else None,
    })
    if plan.status != "success" or plan.rag is None:
        return None

    solve_req = SolveRequest(
        machine_id=machine_id,
        current_state_id=current_state_id,
        target_state_id=target_state_id,
        objective="minimize_makespan",
        status="debug",
    )
    session.add(solve_req)
    await session.flush()
    candidate_plan_id = await save_candidate_plan(plan.rag, solve_req.id, session)
    await session.flush()
    return candidate_plan_id


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solve-request-id", type=int)
    parser.add_argument("--candidate-plan-id", type=int)
    parser.add_argument("--machine-id", type=int)
    parser.add_argument("--current-state-id", type=int)
    parser.add_argument("--target-state-id", type=int)
    parser.add_argument(
        "--commit-debug-plan",
        action="store_true",
        help="Keep a temporary plan created from --machine-id/--current-state-id/--target-state-id.",
    )
    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        candidate_plan_id = args.candidate_plan_id

        if args.solve_request_id is not None:
            request = await session.get(SolveRequest, args.solve_request_id)
            if request is None:
                print(f"Solve request {args.solve_request_id} not found.")
                return
            _print_section("Solve Request", {
                "id": request.id,
                "machine_id": request.machine_id,
                "current_state_id": request.current_state_id,
                "target_state_id": request.target_state_id,
                "status": request.status,
                "objectives": request.objectives,
                "blockage_constraints": request.blockage_constraints,
                "parent_plan_id": request.parent_plan_id,
            })
            candidate_plan_id = await _latest_plan_for_request(session, request.id)
            if candidate_plan_id is None:
                candidate_plan_id = await _create_debug_plan(
                    session,
                    request.machine_id,
                    request.current_state_id,
                    request.target_state_id,
                )

        if candidate_plan_id is None and all(
            value is not None
            for value in (args.machine_id, args.current_state_id, args.target_state_id)
        ):
            current_state = await session.get(MachineState, args.current_state_id)
            target_state = await session.get(MachineState, args.target_state_id)
            if current_state is None or target_state is None:
                print("Current or target state not found.")
                return
            candidate_plan_id = await _create_debug_plan(
                session,
                args.machine_id,
                args.current_state_id,
                args.target_state_id,
            )

        if candidate_plan_id is None:
            parser.error(
                "Pass --solve-request-id, --candidate-plan-id, or "
                "--machine-id with --current-state-id and --target-state-id."
            )

        await _diagnose_existing_plan(session, candidate_plan_id)

        if args.commit_debug_plan:
            await session.commit()
            print(f"\nDebug plan committed: candidate_plan_id={candidate_plan_id}")
        else:
            await session.rollback()
            print("\nRolled back temporary debug data.")


if __name__ == "__main__":
    asyncio.run(main())
