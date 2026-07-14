"""End-to-end contract tests for constraint-driven plan adjustments."""

import pytest
from sqlalchemy import select

from app.db.models import CandidatePlan, CandidatePlanStep, OpRule

from tests.integration.test_step3_api import _do_solve, _seed_base_data


@pytest.mark.asyncio
async def test_schedule_adjustment_preview_and_confirm(client):
    ids = await _seed_base_data(client)
    initial = await _do_solve(client, ids)
    task = next(item for item in initial["schedule"]["tasks"] if item["op_rule_code"] == "OP_CALIBRATE")

    created = await client.post(
        f"/api/v1/plans/{initial['candidate_plan_id']}/adjustments",
        json={"kind": "schedule"},
    )
    assert created.status_code == 200, created.text
    adjustment_id = created.json()["id"]

    patched = await client.patch(
        f"/api/v1/plan-adjustments/{adjustment_id}",
        json={
            "scope_step_ids": [task["step_id"]],
            "constraints": [{
                "type": "not_before",
                "step_ids": [task["step_id"]],
                "value_min": 120,
            }],
        },
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["constraints"][0]["type"] == "not_before"

    preview = await client.post(f"/api/v1/plan-adjustments/{adjustment_id}/preview")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["status"] == "preview_ready"
    assert body["candidate_plan_id"] is not None
    changed = next(item for item in body["task_diffs"] if item["step_order"] == task["step_order"])
    assert changed["new_start_min"] >= 120
    assert body["summary"]["outside_changed_task_count"] >= 0

    restored = await client.get(
        f"/api/v1/solve-requests/{body['summary']['candidate_solve_request_id']}"
    )
    restored_task = next(
        item for item in restored.json()["schedule"]["tasks"]
        if item["step_order"] == task["step_order"]
    )
    assert restored_task["step_role"] == "delayed"

    confirmed = await client.post(f"/api/v1/plan-adjustments/{adjustment_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"

    stale_create = await client.post(
        f"/api/v1/plans/{initial['candidate_plan_id']}/adjustments",
        json={"kind": "schedule"},
    )
    assert stale_create.status_code == 409
    assert stale_create.json()["error_code"] == "PLAN_NOT_BASELINE"


@pytest.mark.asyncio
async def test_confirmed_adjustment_rebases_inherited_constraints_to_new_step_ids(
    client,
    db_session,
):
    ids = await _seed_base_data(client)
    initial = await _do_solve(client, ids)
    task = initial["schedule"]["tasks"][0]
    first = await client.post(
        f"/api/v1/plans/{initial['candidate_plan_id']}/adjustments",
        json={
            "scope_step_ids": [task["step_id"]],
            "constraints": [{
                "type": "not_before",
                "step_ids": [task["step_id"]],
                "value_min": int(task["start_min"]),
            }],
        },
    )
    assert first.status_code == 200, first.text
    first_constraint = first.json()["constraints"][0]
    first_preview = await client.post(
        f"/api/v1/plan-adjustments/{first.json()['id']}/preview"
    )
    assert first_preview.status_code == 200, first_preview.text
    first_candidate_id = first_preview.json()["candidate_plan_id"]
    confirmed = await client.post(
        f"/api/v1/plan-adjustments/{first.json()['id']}/confirm"
    )
    assert confirmed.status_code == 200, confirmed.text

    restored = await client.get(
        f"/api/v1/solve-requests/{first_preview.json()['summary']['candidate_solve_request_id']}"
    )
    current_task = next(
        item for item in restored.json()["schedule"]["tasks"]
        if item["step_order"] == task["step_order"]
    )
    assert current_task["step_id"] != task["step_id"]

    # Simulate the legacy snapshot already present in the user's confirmed
    # baseline: its constraint still points at the parent plan's step ID.
    current_baseline = await db_session.get(CandidatePlan, first_candidate_id)
    current_baseline.adjustment_snapshot = {
        "constraints": [{**first_constraint, "step_ids": [task["step_id"]]}]
    }
    await db_session.commit()

    second = await client.post(
        f"/api/v1/plans/{first_candidate_id}/adjustments",
        json={"scope_step_ids": [current_task["step_id"]]},
    )
    assert second.status_code == 200, second.text
    second_preview = await client.post(
        f"/api/v1/plan-adjustments/{second.json()['id']}/preview"
    )
    assert second_preview.status_code == 200, second_preview.text
    assert second_preview.json()["status"] == "preview_ready"
    assert second_preview.json()["adjustment"]["effective_constraints"][0]["step_ids"] == [
        current_task["step_id"]
    ]

    second_candidate_id = second_preview.json()["candidate_plan_id"]
    step_result = await db_session.execute(
        select(CandidatePlanStep).where(
            CandidatePlanStep.candidate_plan_id == second_candidate_id,
            CandidatePlanStep.step_order == task["step_order"],
        )
    )
    second_candidate_step = step_result.scalar_one()
    second_candidate = await db_session.get(CandidatePlan, second_candidate_id)
    assert second_candidate.adjustment_snapshot["constraints"][0]["step_ids"] == [
        second_candidate_step.id
    ]


@pytest.mark.asyncio
async def test_constraint_must_target_selected_scope(client):
    ids = await _seed_base_data(client)
    initial = await _do_solve(client, ids)
    first, second = initial["schedule"]["tasks"][:2]
    created = await client.post(
        f"/api/v1/plans/{initial['candidate_plan_id']}/adjustments",
        json={
            "scope_step_ids": [first["step_id"]],
            "constraints": [{
                "type": "freeze",
                "step_ids": [second["step_id"]],
            }],
        },
    )
    adjustment_id = created.json()["id"]
    preview = await client.post(f"/api/v1/plan-adjustments/{adjustment_id}/preview")
    assert preview.status_code == 422
    assert preview.json()["error_code"] == "STEP_OUTSIDE_CHANGE_SCOPE"


@pytest.mark.asyncio
async def test_infeasible_adjustment_keeps_draft_diagnostics_without_candidate(client):
    ids = await _seed_base_data(client)
    initial = await _do_solve(client, ids)
    task = initial["schedule"]["tasks"][0]
    created = await client.post(
        f"/api/v1/plans/{initial['candidate_plan_id']}/adjustments",
        json={
            "scope_step_ids": [task["step_id"]],
            "constraints": [
                {"type": "not_before", "step_ids": [task["step_id"]], "value_min": 100},
                {"type": "finish_not_after", "step_ids": [task["step_id"]], "value_min": 10},
            ],
        },
    )
    adjustment_id = created.json()["id"]
    preview = await client.post(f"/api/v1/plan-adjustments/{adjustment_id}/preview")
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["status"] == "infeasible"
    assert body["candidate_plan_id"] is None
    assert body["diagnostics"]["adjustment"]["conflict_constraints"]


@pytest.mark.asyncio
async def test_adjustment_supports_fixed_freeze_finish_priority_and_precedence(client):
    ids = await _seed_base_data(client)
    initial = await _do_solve(client, ids)
    tasks = initial["schedule"]["tasks"]
    first, second, third = tasks[:3]
    fixed_start = int(first["start_min"])
    frozen_start = int(second["start_min"])

    created = await client.post(
        f"/api/v1/plans/{initial['candidate_plan_id']}/adjustments",
        json={
            "scope_step_ids": [first["step_id"], second["step_id"], third["step_id"]],
            "constraints": [
                {"type": "fixed_start", "step_ids": [first["step_id"]], "value_min": fixed_start},
                {"type": "freeze", "step_ids": [second["step_id"]]},
                {
                    "type": "finish_not_after",
                    "step_ids": [second["step_id"]],
                    "value_min": int(second["end_min"]),
                },
                {"type": "priority", "step_ids": [first["step_id"]], "value": "high"},
                {
                    "type": "precedence",
                    "predecessor_step_id": first["step_id"],
                    "successor_step_id": third["step_id"],
                },
            ],
        },
    )
    assert created.status_code == 200, created.text

    preview = await client.post(
        f"/api/v1/plan-adjustments/{created.json()['id']}/preview"
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert body["status"] == "preview_ready"
    by_order = {item["step_order"]: item for item in body["task_diffs"]}
    assert by_order[first["step_order"]]["new_start_min"] == fixed_start
    assert by_order[second["step_order"]]["new_start_min"] == frozen_start
    assert by_order[second["step_order"]]["new_end_min"] <= second["end_min"]
    assert body["diagnostics"]["adjustment_optimization"]


@pytest.mark.asyncio
async def test_artificial_precedence_cycle_is_rejected_before_candidate(client):
    ids = await _seed_base_data(client)
    initial = await _do_solve(client, ids)
    _, second, third = initial["schedule"]["tasks"][:3]
    created = await client.post(
        f"/api/v1/plans/{initial['candidate_plan_id']}/adjustments",
        json={
            "scope_step_ids": [second["step_id"], third["step_id"]],
            "constraints": [{
                "type": "precedence",
                "predecessor_step_id": third["step_id"],
                "successor_step_id": second["step_id"],
            }],
        },
    )
    assert created.status_code == 200, created.text
    preview = await client.post(
        f"/api/v1/plan-adjustments/{created.json()['id']}/preview"
    )
    assert preview.status_code == 422, preview.text
    assert preview.json()["error_code"] == "CONSTRAINT_CYCLE"


@pytest.mark.asyncio
async def test_confirm_marks_sibling_draft_stale_and_restores_step_ids(client):
    ids = await _seed_base_data(client)
    initial = await _do_solve(client, ids)
    task = initial["schedule"]["tasks"][0]
    sibling = await client.post(
        f"/api/v1/plans/{initial['candidate_plan_id']}/adjustments",
        json={"kind": "schedule"},
    )
    chosen = await client.post(
        f"/api/v1/plans/{initial['candidate_plan_id']}/adjustments",
        json={
            "scope_step_ids": [task["step_id"]],
            "constraints": [{
                "type": "not_before",
                "step_ids": [task["step_id"]],
                "value_min": int(task["start_min"]),
            }],
        },
    )
    preview = await client.post(
        f"/api/v1/plan-adjustments/{chosen.json()['id']}/preview"
    )
    solve_request_id = preview.json()["summary"]["candidate_solve_request_id"]
    confirmed = await client.post(
        f"/api/v1/plan-adjustments/{chosen.json()['id']}/confirm"
    )
    assert confirmed.status_code == 200, confirmed.text
    sibling_read = await client.get(
        f"/api/v1/plan-adjustments/{sibling.json()['id']}"
    )
    assert sibling_read.json()["status"] == "stale"

    restored = await client.get(f"/api/v1/solve-requests/{solve_request_id}")
    assert restored.status_code == 200, restored.text
    restored_task = restored.json()["schedule"]["tasks"][0]
    assert restored_task["step_id"] is not None
    assert restored_task["lineage_key"]


@pytest.mark.asyncio
async def test_full_replan_candidate_requires_explicit_baseline_confirmation(client):
    ids = await _seed_base_data(client)
    baseline = await _do_solve(client, ids)
    candidate = await _do_solve(
        client,
        ids,
        parent_plan_id=baseline["candidate_plan_id"],
    )
    registered = await client.post(
        f"/api/v1/plans/{baseline['candidate_plan_id']}/adjustments",
        json={
            "kind": "rule_exception",
            "scope_step_ids": [baseline["schedule"]["tasks"][0]["step_id"]],
            "candidate_plan_id": candidate["candidate_plan_id"],
        },
    )
    assert registered.status_code == 200, registered.text
    body = registered.json()
    assert body["status"] == "preview_ready"
    assert body["candidate_plan_id"] == candidate["candidate_plan_id"]
    assert body["preview_summary"]["candidate_solve_request_id"] == candidate["solve_request_id"]

    confirmed = await client.post(
        f"/api/v1/plan-adjustments/{body['id']}/confirm"
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["status"] == "confirmed"


@pytest.mark.asyncio
async def test_ordinary_adjustment_preserves_activity_duration_and_system_dependencies(
    client,
    db_session,
):
    ids = await _seed_base_data(client)
    baseline = await _do_solve(client, ids)
    task = baseline["schedule"]["tasks"][-1]
    created = await client.post(
        f"/api/v1/plans/{baseline['candidate_plan_id']}/adjustments",
        json={
            "scope_step_ids": [task["step_id"]],
            "constraints": [{
                "type": "not_before",
                "step_ids": [task["step_id"]],
                "value_min": int(task["start_min"]) + 10,
            }],
        },
    )
    preview = await client.post(
        f"/api/v1/plan-adjustments/{created.json()['id']}/preview"
    )
    assert preview.status_code == 200, preview.text
    candidate_id = preview.json()["candidate_plan_id"]

    result = await db_session.execute(
        select(CandidatePlanStep)
        .where(CandidatePlanStep.candidate_plan_id.in_([
            baseline["candidate_plan_id"], candidate_id,
        ]))
        .order_by(CandidatePlanStep.candidate_plan_id, CandidatePlanStep.step_order)
    )
    by_plan = {}
    for step in result.scalars().all():
        by_plan.setdefault(step.candidate_plan_id, []).append(step)
    base_steps = by_plan[baseline["candidate_plan_id"]]
    candidate_steps = by_plan[candidate_id]
    assert [step.lineage_key for step in candidate_steps] == [step.lineage_key for step in base_steps]
    assert [step.op_rule_id for step in candidate_steps] == [step.op_rule_id for step in base_steps]
    assert [step.predecessor_ids for step in candidate_steps] == [step.predecessor_ids for step in base_steps]

    rules = await db_session.execute(
        select(OpRule).where(OpRule.id.in_([step.op_rule_id for step in base_steps]))
    )
    duration_by_rule = {rule.id: rule.duration_min for rule in rules.scalars().all()}
    assert [duration_by_rule[step.op_rule_id] for step in candidate_steps] == [
        duration_by_rule[step.op_rule_id] for step in base_steps
    ]
