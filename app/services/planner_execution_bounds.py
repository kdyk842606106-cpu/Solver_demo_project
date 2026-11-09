"""Per-run search bounds, separate from saved scenario/business constraints."""
from __future__ import annotations

from app.services.planner_scenarios import expand_packages


def automatic_solver_budget(scenario: dict) -> dict:
    """Bounded server policy, versioned and frozen when the job is enqueued."""
    count = len(expand_packages(scenario).get("activities", []))
    seconds = 60 if count <= 64 else 120 if count <= 256 else 300
    return {"mode": "auto", "policy": "activity_tiers_v1",
            "activity_count": count, "time_limit_seconds": seconds}


def automatic_execution_bound(scenario: dict) -> dict:
    # Count definitions in the effective scope, never package references.
    activities = expand_packages(scenario).get("activities", [])
    limited = [a for a in activities if a.get("max_instances") is not None]
    unlimited_count = len(activities) - len(limited)
    finite_sum = sum(int(a["max_instances"]) for a in limited)
    destructive_count = sum(
        bool(a.get("delete_effect_state_ids"))
        or any(p.get("relation_role") == "transition" for p in a.get("preconditions", []))
        for a in activities
    )
    if not unlimited_count:
        # This does not exclude any plan allowed by activity-level limits.
        value = max(1, finite_sum)
        policy = "sum_activity_limits"
    else:
        # A practical finite search envelope, NOT a completeness theorem.
        # Reserve two occurrences per uncapped activity plus restoration room.
        value = max(
            20,
            finite_sum + 2 * unlimited_count + 2 * destructive_count
            + len(set(scenario.get("goal_state_ids", []))),
        )
        policy = "repeat_allowance_v1"
    return {
        "mode": "auto",
        "value": value,
        "policy": policy,
        "activity_count": len(activities),
        "unlimited_activity_count": unlimited_count,
        "heuristic": bool(unlimited_count),
    }
