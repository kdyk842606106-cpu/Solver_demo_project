"""Unit tests for the forward BFS planner core."""

from dataclasses import dataclass, field

from app.core.planner.bfs import BfsLimits, forward_bfs_plan


@dataclass
class MockPrecond:
    feature_key: str
    operator: str
    feature_value: str
    value_list: list | None = None


@dataclass
class MockEffect:
    feature_key: str
    new_value: str = ""
    effect_type: str = "set"
    delta_value: float | None = None


@dataclass
class MockRule:
    id: int
    code: str
    duration_min: int
    preconditions: list[MockPrecond] = field(default_factory=list)
    effects: list[MockEffect] = field(default_factory=list)


@dataclass
class MockFeatureDef:
    value_type: str


def test_forward_bfs_finds_multistep_precondition_chain():
    warmup = MockRule(
        id=1,
        code="OP_WARMUP",
        duration_min=10,
        effects=[MockEffect("temperature", "hot")],
    )
    calibrate = MockRule(
        id=2,
        code="OP_CALIBRATE",
        duration_min=5,
        preconditions=[MockPrecond("temperature", "eq", "hot")],
        effects=[MockEffect("calibration", "on")],
    )

    result = forward_bfs_plan(
        current_state={"temperature": "cold", "calibration": "off"},
        target_state={"temperature": "hot", "calibration": "on"},
        rules=[calibrate, warmup],
        feature_defs={},
    )

    assert result.status == "success"
    assert [step.rule.code for step in result.path] == ["OP_WARMUP", "OP_CALIBRATE"]
    assert result.diagnostics["rules_count"] == 2
    assert result.diagnostics["path_length"] == 2
    assert result.diagnostics["limit_type"] is None
    assert result.diagnostics["unmatched_goal_features"] == []
    assert result.diagnostics["rule_checks"] > 0
    assert result.diagnostics["executable_transitions"] >= 2
    assert result.diagnostics["enqueued_nodes"] >= 2
    assert result.diagnostics["top_enqueued_rules"]


def test_forward_bfs_repeats_numeric_rule_instances():
    fill = MockRule(
        id=1,
        code="OP_FILL",
        duration_min=5,
        effects=[MockEffect("water_level", effect_type="increment", delta_value=20)],
    )

    result = forward_bfs_plan(
        current_state={"water_level": "0"},
        target_state={"water_level": "40"},
        rules=[fill],
        feature_defs={"water_level": MockFeatureDef("number")},
    )

    assert result.status == "success"
    assert [step.rule.code for step in result.path] == ["OP_FILL", "OP_FILL"]
    assert result.final_state["water_level"] == "40"


def test_forward_bfs_reports_no_solution_when_depth_limit_blocks_path():
    fill = MockRule(
        id=1,
        code="OP_FILL",
        duration_min=5,
        effects=[MockEffect("water_level", effect_type="increment", delta_value=10)],
    )

    result = forward_bfs_plan(
        current_state={"water_level": "0"},
        target_state={"water_level": "40"},
        rules=[fill],
        feature_defs={"water_level": MockFeatureDef("number")},
        limits=BfsLimits(max_depth=2, max_nodes=20),
    )

    assert result.status == "no_solution"
    assert result.error_code == "BFS_LIMIT_EXCEEDED"
    assert result.diagnostics["limit_type"] == "max_depth"
    assert result.diagnostics["max_depth_seen"] == 2
    assert result.diagnostics["unmatched_goal_features"] == ["water_level"]
    assert result.diagnostics["rule_checks"] == 2
    assert result.diagnostics["depth_enqueued"] == {"1": 1, "2": 1}


def test_forward_bfs_diagnostics_report_node_limit():
    rules = [
        MockRule(
            id=idx,
            code=f"OP_NOISE_{idx}",
            duration_min=5,
            effects=[MockEffect(f"noise_{idx}", "on")],
        )
        for idx in range(1, 6)
    ]

    result = forward_bfs_plan(
        current_state={"target": "off"},
        target_state={"target": "on"},
        rules=rules,
        feature_defs={},
        limits=BfsLimits(max_depth=10, max_nodes=3),
    )

    assert result.status == "no_solution"
    assert result.error_code == "BFS_LIMIT_EXCEEDED"
    assert result.diagnostics["limit_type"] == "max_nodes"
    assert result.diagnostics["expanded_nodes"] == 4
    assert result.diagnostics["visited_count"] > result.diagnostics["expanded_nodes"]
    assert result.diagnostics["branching_factor"] > 1
    assert result.diagnostics["skip_reason_counts"]["duplicate_state"] > 0
