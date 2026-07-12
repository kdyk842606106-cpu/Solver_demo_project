from app.core.scheduler.diagnostics import diagnose_schedule_inputs, topological_blockers
from app.core.scheduler.loader import RagData, ResourceData, StepData


def test_diagnose_resource_demand_exceeds_capacity():
    rag = RagData(
        candidate_plan_id=1,
        steps=[
            StepData(
                step_order=1,
                op_rule_id=10,
                op_rule_code="OP_HEAVY",
                op_rule_name="Heavy op",
                duration_min=5,
                resource_reqs=[{"resource_type": "TECH", "quantity": 2}],
            )
        ],
        edges=[],
    )
    diagnostics = diagnose_schedule_inputs(
        rag,
        [ResourceData(id=1, code="TECH-01", name="Tech", resource_type="TECH", capacity=1)],
    )

    assert diagnostics["likely_causes"] == ["resource_demand_exceeds_capacity"]
    assert diagnostics["over_capacity_steps"] == [
        {
            "step_order": 1,
            "op_rule_id": 10,
            "op_rule_code": "OP_HEAVY",
            "resource_type": "TECH",
            "demand": 2,
            "available_capacity": 1,
        }
    ]


def test_diagnose_cycle_and_topological_blockers():
    rag = RagData(
        candidate_plan_id=1,
        steps=[
            StepData(1, 10, "A", "A", 5),
            StepData(2, 20, "B", "B", 5),
        ],
        edges=[(1, 2), (2, 1)],
    )

    diagnostics = diagnose_schedule_inputs(rag, [])
    topology = topological_blockers(rag)

    assert diagnostics["cycle_path"] == [1, 2, 1]
    assert "rag_cycle" in diagnostics["likely_causes"]
    assert topology["blocked_step_orders"] == [1, 2]
