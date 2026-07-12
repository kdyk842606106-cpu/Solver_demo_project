"""
Direct solver script for OPS integration.

Bypasses Planner and directly creates candidate_plan + steps,
then calls Scheduler to solve.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal
from app.db.models import (
    CandidatePlan,
    CandidatePlanStep,
    OpRule,
    SolveRequest,
    Machine,
    ScheduleResult,
)
from app.core.scheduler.solver import solve_schedule, format_schedule
from app.core.scheduler.solver import ScheduleResultData
from sqlalchemy import select


# OPS dependencies mapping
OPS_DEPS = {
    "MS010-OPS001": [],
    "MS010-OPS002": ["MS010-OPS001"],
    "MS010-OPS003": ["MS010-OPS002"],
    "MS010-OPS004": ["MS010-OPS003"],
    "MS010-OPS005": ["MS010-OPS004"],
    "MS010-OPS006": ["MS010-OPS005"],
    "MS010-OPS007": ["MS010-OPS006"],
    "MS010-OPS008": ["MS010-OPS004", "MS010-OPS005"],
    "MS010-OPS009": ["MS010-OPS008"],
    "MS010-OPS010": ["MS010-OPS009", "MS010-OPS007"],
    "MS010-OPS011": ["MS010-OPS010"],
    "MS010-OPS012": ["MS010-OPS009", "MS010-OPS004"],
    "MS010-OPS013": ["MS010-OPS012"],
    "MS010-OPS014": ["MS010-OPS013"],
    "MS010-OPS015": ["MS010-OPS004"],
    "MS010-OPS016": ["MS010-OPS015", "MS010-OPS004"],
    "MS010-OPS017": ["MS010-OPS004"],
    "MS010-OPS018": ["MS010-OPS017"],
    "MS010-OPS019": ["MS010-OPS018"],
    "MS010-OPS020": ["MS010-OPS019"],
    "MS010-OPS021": ["MS010-OPS020"],
    "MS010-OPS022": ["MS010-OPS021"],
    "MS010-OPS023": ["MS010-OPS022"],
    "MS010-OPS024": ["MS010-OPS023"],
    "MS010-OPS025": ["MS010-OPS014"],
    "MS010-OPS026": ["MS010-OPS025", "MS010-OPS016"],
    "MS010-OPS027": ["MS010-OPS026"],
}


async def get_op_rule_map(session: AsyncSession) -> dict[str, int]:
    """Get op_rule ID mapping."""
    result = await session.execute(
        select(OpRule).where(OpRule.id >= 9000)
    )
    rules = result.scalars().all()
    return {r.code: r.id for r in rules}


async def main():
    async with AsyncSessionLocal() as session:
        # Get op_rule mapping
        op_rule_map = await get_op_rule_map(session)
        print(f"Loaded {len(op_rule_map)} op_rules")

        # Get machine
        result = await session.execute(select(Machine).where(Machine.id == 9001))
        machine = result.scalar_one()
        print(f"Machine: {machine.code}")

        # Create solve_request
        solve_req = SolveRequest(
            machine_id=machine.id,
            current_state_id=9001,
            target_state_id=9002,
            objective="minimize_makespan",
            status="running",
        )
        session.add(solve_req)
        await session.flush()
        print(f"SolveRequest created: {solve_req.id}")

        # Create candidate_plan
        plan = CandidatePlan(
            solve_request_id=solve_req.id,
            total_steps=len(OPS_DEPS),
            search_method="direct_import",
            status="draft",
        )
        session.add(plan)
        await session.flush()
        print(f"CandidatePlan created: {plan.id}")

        # Create steps with dependencies
        # We need to map op_rule IDs to step_orders
        code_to_step = {code: i + 1 for i, code in enumerate(OPS_DEPS.keys())}

        for code, deps in OPS_DEPS.items():
            op_id = op_rule_map[code]
            step_order = code_to_step[code]
            predecessor_ids = [code_to_step[d] for d in deps]

            step = CandidatePlanStep(
                candidate_plan_id=plan.id,
                step_order=step_order,
                op_rule_id=op_id,
                predecessor_ids=predecessor_ids,
                not_before=None,
                step_role="normal",
            )
            session.add(step)

        await session.flush()
        print(f"Created {len(OPS_DEPS)} steps")

        # Call scheduler
        print("\nSolving schedule...")
        result = await solve_schedule(
            candidate_plan_id=plan.id,
            session=session,
            max_time_seconds=30.0,
        )

        if result.status in ("optimal", "feasible"):
            print(f"\n[SUCCESS] Schedule {result.status.upper()}")
            print(f"Makespan: {result.makespan} min ({result.makespan / 60:.1f} h)")
            print(f"\nTasks:")
            for t in result.tasks:
                preds = f" (after {t.predecessors})" if t.predecessors else ""
                res = ", ".join(r["resource_code"] for r in t.resources) or "unassigned"
                print(
                    f"  Step {t.step_order:2d}: {t.op_rule_code:30s} "
                    f"start={t.start_min:5d} end={t.end_min:5d} "
                    f"dur={t.duration_min:3d} res={res}{preds}"
                )

            if result.parallel_groups:
                print(f"\nParallel groups: {len(result.parallel_groups)}")
                for g in result.parallel_groups:
                    print(f"  Steps {g}")

            # Save result
            schedule_result = ScheduleResult(
                solve_request_id=solve_req.id,
                candidate_plan_id=plan.id,
                makespan=result.makespan,
                solver_status=result.solver_stats.solver_status if result.solver_stats else None,
                tasks=[
                    {
                        "step_order": t.step_order,
                        "op_rule_id": t.op_rule_id,
                        "op_rule_code": t.op_rule_code,
                        "op_rule_name": t.op_rule_name,
                        "start_min": t.start_min,
                        "end_min": t.end_min,
                        "duration_min": t.duration_min,
                        "predecessors": t.predecessors,
                        "resources": t.resources,
                    }
                    for t in result.tasks
                ],
            )
            session.add(schedule_result)
            await session.commit()
            print(f"\nScheduleResult saved: id={schedule_result.id}")

        else:
            print(f"\n[FAILED] Schedule failed: {result.status}")
            print(f"Error: {result.error_message}")

        return result


if __name__ == "__main__":
    result = asyncio.run(main())
