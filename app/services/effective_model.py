"""Canonical effective-model resolver shared by precheck and solve.

The resolver is the single boundary where legacy package scopes are adapted.
Its output contains only canonical state facts, canonical atomic activities,
and their effective rules. Display references and package paths never become
solver identities.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.schemas import LayeredExpansionRequest
from app.services.layered_expansion import expand_layered_context
from app.services.layered_health import check_layered_health


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


async def resolve_effective_model(
    session: AsyncSession,
    machine_type_id: int,
    payload: LayeredExpansionRequest,
    *,
    additional_goal_facts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Resolve and fingerprint the canonical model used by validation/solve."""

    expansion = await expand_layered_context(session, machine_type_id, payload)
    if additional_goal_facts:
        expansion = {
            **expansion,
            "goal_facts": [
                *expansion["goal_facts"],
                *additional_goal_facts,
            ],
        }
    health = await check_layered_health(
        session,
        machine_type_id,
        payload,
        expansion=expansion,
    )
    canonical_atomic_activity_ids = sorted({
        int(candidate["atomic_activity_id"])
        for candidate in expansion["candidate_activities"]
        if candidate.get("atomic_activity_id") is not None
    })
    snapshot = {
        "schema_version": "effective-model/v1",
        "machine_type_id": machine_type_id,
        "goal_facts": expansion["goal_facts"],
        "candidate_activities": expansion["candidate_activities"],
        "effective_rules": expansion["effective_rules"],
    }
    version = hashlib.sha256(_stable_json(snapshot).encode("utf-8")).hexdigest()
    return {
        "version": f"sha256:{version}",
        "summary": {
            "goal_fact_count": len(expansion["goal_facts"]),
            "canonical_atomic_activity_count": len(canonical_atomic_activity_ids),
            "effective_rule_count": len(expansion["effective_rules"]),
            "blocking_count": health["summary"]["blocking_count"],
        },
        "canonical_atomic_activity_ids": canonical_atomic_activity_ids,
        "snapshot": snapshot,
        "expansion": expansion,
        "health": health,
    }
