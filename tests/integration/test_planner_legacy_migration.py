import pytest
from sqlalchemy import func, select

from app.db.models import (
    ActivityPackageAtomicRef,
    ActivityNode,
    ActivityStateBinding,
    AtomicActivity,
    MachineType,
    OpRule,
    OpRuleEffect,
    OpRulePrecond,
    PlannerScenarioRecord,
    StateNode,
)


async def _seed_legacy(session):
    session.add(MachineType(id=81, code="LEGACY_81", name="旧模型"))
    root = ActivityNode(id=8101, machine_type_id=81, level=1, code="ROOT", name="一级包", sort_order=1)
    child = ActivityNode(id=8102, machine_type_id=81, parent_id=8101, level=2, code="CHILD", name="二级包", sort_order=1)
    atomic = AtomicActivity(id=8201, machine_type_id=81, code="DO_WORK", name="执行工作", sort_order=1)
    ready = StateNode(id=8301, machine_type_id=81, level=1, code="READY", name="就绪", feature_key="phase", operator="eq", target_value="ready", state_kind="atomic")
    done = StateNode(id=8302, machine_type_id=81, level=1, code="DONE", name="完成", feature_key="phase", operator="eq", target_value="done", state_kind="atomic")
    rule = OpRule(id=8401, machine_type_id=81, atomic_activity_id=8201, code="RULE_WORK", name="工作规则", duration_min=5, is_active=True)
    session.add_all([root, child, atomic, ready, done, rule])
    await session.flush()
    session.add_all([
        ActivityPackageAtomicRef(id=8501, activity_node_id=8102, atomic_activity_id=8201, sort_order=1),
        OpRulePrecond(id=8601, op_rule_id=8401, feature_key="phase", operator="eq", feature_value="ready"),
        OpRuleEffect(id=8701, op_rule_id=8401, feature_key="phase", new_value="done", effect_type="set"),
        ActivityStateBinding(id=8801, machine_type_id=81, atomic_activity_id=8201, op_rule_id=8401, state_node_id=8301, binding_role="input", binding_type="atomic_state", coverage_policy="snapshot", covered_leaf_state_ids=[8301], coverage_status="complete"),
        ActivityStateBinding(id=8802, machine_type_id=81, atomic_activity_id=8201, op_rule_id=8401, state_node_id=8302, binding_role="output", binding_type="atomic_state", coverage_policy="snapshot", covered_leaf_state_ids=[8302], coverage_status="complete"),
    ])
    await session.commit()


@pytest.mark.asyncio
async def test_legacy_migration_preview_and_execute_leave_legacy_tables_untouched(client, db_session):
    await _seed_legacy(db_session)
    preview = await client.get("/api/v1/planner-migrations/legacy/preview", params={"machine_type_id": 81, "scenario_name": "迁移场景"})
    assert preview.status_code == 200, preview.text
    report = preview.json()["report"]
    assert report["executable"] is True, report
    assert report["create_counts"]["activities"] == 1
    assert report["create_counts"]["state_packages"] == 2

    denied = await client.post("/api/v1/planner-migrations/legacy", json={"machine_type_id": 81, "scenario_name": "迁移场景", "backup_acknowledged": False, "confirm": True})
    assert denied.status_code == 422
    executed = await client.post("/api/v1/planner-migrations/legacy", json={"machine_type_id": 81, "scenario_name": "迁移场景", "backup_acknowledged": True, "confirm": True})
    assert executed.status_code == 201, executed.text
    assert executed.json()["legacy_tables_mutated"] is False

    assert await db_session.scalar(select(func.count(ActivityNode.id)).where(ActivityNode.machine_type_id == 81)) == 2
    assert await db_session.scalar(select(func.count(AtomicActivity.id)).where(AtomicActivity.machine_type_id == 81)) == 1
    assert await db_session.scalar(select(func.count(PlannerScenarioRecord.id))) == 1
