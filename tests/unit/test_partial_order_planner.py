"""Unit tests for the instance-level Partial Order Planner."""

from dataclasses import dataclass, field

from app.core.planner.partial_order import partial_order_plan


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


def test_pop_selects_single_goal_provider():
    warmup = MockRule(
        id=1,
        code="OP_WARMUP",
        duration_min=10,
        effects=[MockEffect("temperature", "hot")],
    )

    result = partial_order_plan(
        current_state={"temperature": "cold"},
        target_state={"temperature": "hot"},
        rules=[warmup],
        feature_defs={},
    )

    assert result.status == "success"
    assert [node.op_rule_code for node in result.nodes] == ["OP_WARMUP"]
    assert result.diagnostics["planner_strategy"] == "partial_order"
    assert result.diagnostics["selected_instance_count"] == 1


def test_pop_reuses_shared_provider_once():
    provide_power = MockRule(
        id=1,
        code="OP_POWER_ON",
        duration_min=5,
        effects=[MockEffect("power", "on")],
    )
    do_a = MockRule(
        id=2,
        code="OP_A",
        duration_min=10,
        preconditions=[MockPrecond("power", "eq", "on")],
        effects=[MockEffect("a_done", "yes")],
    )
    do_b = MockRule(
        id=3,
        code="OP_B",
        duration_min=10,
        preconditions=[MockPrecond("power", "eq", "on")],
        effects=[MockEffect("b_done", "yes")],
    )

    result = partial_order_plan(
        current_state={"power": "off", "a_done": "no", "b_done": "no"},
        target_state={"power": "off", "a_done": "yes", "b_done": "yes"},
        rules=[do_a, do_b, provide_power],
        feature_defs={},
    )

    assert result.status == "success"
    codes = [node.op_rule_code for node in result.nodes]
    assert codes.count("OP_POWER_ON") == 1
    assert codes.count("OP_A") == 1
    assert codes.count("OP_B") == 1


def test_pop_prefers_one_rule_that_satisfies_multiple_goals():
    one = MockRule(
        id=1,
        code="OP_G1",
        duration_min=5,
        effects=[MockEffect("g1", "yes")],
    )
    two = MockRule(
        id=2,
        code="OP_G2",
        duration_min=5,
        effects=[MockEffect("g2", "yes")],
    )
    combined = MockRule(
        id=3,
        code="OP_BOTH",
        duration_min=20,
        effects=[MockEffect("g1", "yes"), MockEffect("g2", "yes")],
    )

    result = partial_order_plan(
        current_state={"g1": "no", "g2": "no"},
        target_state={"g1": "yes", "g2": "yes"},
        rules=[one, two, combined],
        feature_defs={},
    )

    assert result.status == "success"
    assert [node.op_rule_code for node in result.nodes] == ["OP_BOTH"]


def test_pop_repeats_numeric_increment_instances():
    fill = MockRule(
        id=1,
        code="OP_FILL",
        duration_min=5,
        effects=[MockEffect("water_level", effect_type="increment", delta_value=20)],
    )

    result = partial_order_plan(
        current_state={"water_level": "0"},
        target_state={"water_level": "40"},
        rules=[fill],
        feature_defs={"water_level": MockFeatureDef("number")},
    )

    assert result.status == "success"
    assert [node.op_rule_code for node in result.nodes] == ["OP_FILL", "OP_FILL"]
    assert [node.predecessors for node in result.nodes] == [[], [1]]


def test_pop_inserts_numeric_precondition_support_chain():
    fill = MockRule(
        id=1,
        code="OP_FILL",
        duration_min=5,
        preconditions=[MockPrecond("pressure", "gte", "2")],
        effects=[MockEffect("water_level", effect_type="increment", delta_value=20)],
    )
    pressurize = MockRule(
        id=2,
        code="OP_PRESSURIZE",
        duration_min=3,
        effects=[MockEffect("pressure", effect_type="increment", delta_value=1)],
    )

    result = partial_order_plan(
        current_state={"water_level": "0", "pressure": "0"},
        target_state={"water_level": "40", "pressure": "0"},
        rules=[fill, pressurize],
        feature_defs={
            "water_level": MockFeatureDef("number"),
            "pressure": MockFeatureDef("number"),
        },
    )

    assert result.status == "success"
    codes = [node.op_rule_code for node in result.nodes]
    assert codes.count("OP_PRESSURIZE") == 2
    assert codes.count("OP_FILL") == 2


def test_pop_rejects_impossible_cycle():
    fill = MockRule(
        id=1,
        code="OP_FILL",
        duration_min=5,
        preconditions=[MockPrecond("pressure", "gte", "2")],
        effects=[MockEffect("water_level", effect_type="increment", delta_value=20)],
    )
    pressurize = MockRule(
        id=2,
        code="OP_PRESSURIZE",
        duration_min=3,
        preconditions=[MockPrecond("water_level", "gte", "20")],
        effects=[MockEffect("pressure", effect_type="increment", delta_value=1)],
    )

    result = partial_order_plan(
        current_state={"water_level": "0", "pressure": "0"},
        target_state={"water_level": "40", "pressure": "0"},
        rules=[fill, pressurize],
        feature_defs={
            "water_level": MockFeatureDef("number"),
            "pressure": MockFeatureDef("number"),
        },
    )

    assert result.status == "no_solution"


def test_pop_transitive_reduction_removes_redundant_edges():
    a = MockRule(id=1, code="OP_A", duration_min=1, effects=[MockEffect("a", "yes")])
    b = MockRule(
        id=2,
        code="OP_B",
        duration_min=1,
        preconditions=[MockPrecond("a", "eq", "yes")],
        effects=[MockEffect("b", "yes")],
    )
    c = MockRule(
        id=3,
        code="OP_C",
        duration_min=1,
        preconditions=[
            MockPrecond("a", "eq", "yes"),
            MockPrecond("b", "eq", "yes"),
        ],
        effects=[MockEffect("c", "yes")],
    )

    result = partial_order_plan(
        current_state={"a": "no", "b": "no", "c": "no"},
        target_state={"a": "yes", "b": "yes", "c": "yes"},
        rules=[a, b, c],
        feature_defs={},
    )

    assert result.status == "success"
    assert len(result.edges) == 2


def test_pop_reprovider_inserts_repeated_cleaning_for_unmet_numeric_precondition():
    mechanical = MockRule(
        id=1,
        code="OP_MECH",
        duration_min=5,
        preconditions=[MockPrecond("cleanliness", "gt", "30")],
        effects=[
            MockEffect("progress", effect_type="increment", delta_value=1),
            MockEffect("cleanliness", effect_type="sub", delta_value=25),
        ],
    )
    clean = MockRule(
        id=2,
        code="OP_CLEAN",
        duration_min=3,
        effects=[MockEffect("cleanliness", new_value="100", effect_type="reset")],
    )

    result = partial_order_plan(
        current_state={"progress": "0", "cleanliness": "100"},
        target_state={"progress": "7", "cleanliness": "100"},
        rules=[mechanical, clean],
        feature_defs={
            "progress": MockFeatureDef("number"),
            "cleanliness": MockFeatureDef("number"),
        },
    )

    assert result.status == "success"
    codes = [node.op_rule_code for node in result.nodes]
    assert codes.count("OP_MECH") == 7
    assert codes.count("OP_CLEAN") == 3
    assert result.diagnostics["reprovider_insertion_count"] == 3
    assert result.diagnostics["final_state_repaired"] is True


def test_pop_reprovider_repowers_after_power_off_for_later_consumer():
    power_on = MockRule(
        id=1,
        code="OP_POWER_ON",
        duration_min=2,
        effects=[MockEffect("power", "on")],
    )
    power_off = MockRule(
        id=2,
        code="OP_POWER_OFF",
        duration_min=2,
        effects=[MockEffect("power", "off")],
    )
    vacuum = MockRule(
        id=3,
        code="OP_VACUUM",
        duration_min=5,
        preconditions=[MockPrecond("power", "eq", "off")],
        effects=[MockEffect("vacuum_done", "yes")],
    )
    test_b = MockRule(
        id=4,
        code="OP_TEST_B",
        duration_min=5,
        preconditions=[
            MockPrecond("vacuum_done", "eq", "yes"),
            MockPrecond("power", "eq", "on"),
        ],
        effects=[MockEffect("test_b", "done")],
    )

    result = partial_order_plan(
        current_state={"power": "on", "vacuum_done": "no", "test_b": "todo"},
        target_state={"power": "on", "vacuum_done": "yes", "test_b": "done"},
        rules=[power_on, power_off, vacuum, test_b],
        feature_defs={},
    )

    assert result.status == "success"
    codes = [node.op_rule_code for node in result.nodes]
    assert codes.count("OP_POWER_OFF") == 1
    assert codes.count("OP_POWER_ON") == 1
    assert codes.count("OP_VACUUM") == 1
    assert codes.count("OP_TEST_B") == 1
    by_code = {node.op_rule_code: node for node in result.nodes}
    assert by_code["OP_POWER_ON"].id in by_code["OP_TEST_B"].predecessors
    assert by_code["OP_POWER_OFF"].id in by_code["OP_VACUUM"].predecessors
    assert by_code["OP_VACUUM"].id in by_code["OP_POWER_ON"].predecessors


def test_pop_reprovider_keeps_unrelated_branch_parallel():
    mechanical = MockRule(
        id=1,
        code="OP_MECH",
        duration_min=5,
        preconditions=[MockPrecond("cleanliness", "gt", "30")],
        effects=[
            MockEffect("progress", effect_type="increment", delta_value=1),
            MockEffect("cleanliness", effect_type="sub", delta_value=25),
        ],
    )
    clean = MockRule(
        id=2,
        code="OP_CLEAN",
        duration_min=3,
        effects=[MockEffect("cleanliness", new_value="100", effect_type="reset")],
    )
    independent = MockRule(
        id=3,
        code="OP_INDEPENDENT",
        duration_min=1,
        effects=[MockEffect("branch_done", "yes")],
    )

    result = partial_order_plan(
        current_state={"progress": "0", "cleanliness": "100", "branch_done": "no"},
        target_state={"progress": "4", "cleanliness": "100", "branch_done": "yes"},
        rules=[mechanical, clean, independent],
        feature_defs={
            "progress": MockFeatureDef("number"),
            "cleanliness": MockFeatureDef("number"),
        },
    )

    assert result.status == "success"
    independent_node = next(node for node in result.nodes if node.op_rule_code == "OP_INDEPENDENT")
    clean_nodes = [node for node in result.nodes if node.op_rule_code == "OP_CLEAN"]
    assert clean_nodes
    assert independent_node.predecessors == []
    assert all(independent_node.id not in node.predecessors for node in clean_nodes)


def _code_positions(result):
    return {node.op_rule_code: index for index, node in enumerate(result.nodes)}


def test_pop_orders_initial_window_consumer_before_breaker():
    install_a = MockRule(
        id=1,
        code="OP_INSTALL_A",
        duration_min=10,
        effects=[MockEffect("module_a", "installed")],
    )
    install_c = MockRule(
        id=2,
        code="OP_INSTALL_C",
        duration_min=10,
        preconditions=[
            MockPrecond("module_a", "eq", "installed"),
            MockPrecond("fixture_b", "eq", "uninstalled"),
        ],
        effects=[MockEffect("module_c", "installed")],
    )
    install_fixture_b = MockRule(
        id=3,
        code="OP_INSTALL_FIXTURE_B",
        duration_min=10,
        preconditions=[
            MockPrecond("fixture_b", "eq", "uninstalled"),
            MockPrecond("module_c", "eq", "uninstalled"),
        ],
        effects=[MockEffect("fixture_b", "installed")],
    )
    install_b = MockRule(
        id=4,
        code="OP_INSTALL_B",
        duration_min=10,
        preconditions=[
            MockPrecond("module_a", "eq", "installed"),
            MockPrecond("fixture_b", "eq", "installed"),
        ],
        effects=[MockEffect("module_b", "installed")],
    )
    remove_fixture_b = MockRule(
        id=5,
        code="OP_REMOVE_FIXTURE_B",
        duration_min=10,
        preconditions=[MockPrecond("fixture_b", "eq", "installed")],
        effects=[MockEffect("fixture_b", "uninstalled")],
    )

    result = partial_order_plan(
        current_state={
            "module_a": "uninstalled",
            "module_b": "uninstalled",
            "module_c": "uninstalled",
            "fixture_b": "uninstalled",
        },
        target_state={
            "module_a": "installed",
            "module_b": "installed",
            "module_c": "installed",
            "fixture_b": "uninstalled",
        },
        rules=[install_a, install_c, install_fixture_b, install_b, remove_fixture_b],
        feature_defs={},
    )

    assert result.status == "success"
    positions = _code_positions(result)
    assert positions["OP_INSTALL_FIXTURE_B"] < positions["OP_INSTALL_B"]
    assert positions["OP_INSTALL_B"] < positions["OP_REMOVE_FIXTURE_B"]
    assert positions["OP_REMOVE_FIXTURE_B"] < positions["OP_INSTALL_C"]
    assert result.diagnostics["initial_window_ordering_count"] >= 1


def test_pop_repairs_multiple_initial_windows_one_replay_at_a_time():
    install_c = MockRule(
        id=1,
        code="OP_INSTALL_C",
        duration_min=10,
        effects=[
            MockEffect("module_c", "installed"),
            MockEffect("module_c_slot", "closed"),
        ],
    )
    install_e = MockRule(
        id=2,
        code="OP_INSTALL_E",
        duration_min=10,
        effects=[
            MockEffect("module_e", "installed"),
            MockEffect("module_e_slot", "closed"),
        ],
    )
    use_c_slot = MockRule(
        id=3,
        code="OP_USE_C_SLOT",
        duration_min=10,
        preconditions=[MockPrecond("module_c_slot", "eq", "open")],
        effects=[MockEffect("c_tooling_done", "yes")],
    )
    use_e_slot = MockRule(
        id=4,
        code="OP_USE_E_SLOT",
        duration_min=10,
        preconditions=[MockPrecond("module_e_slot", "eq", "open")],
        effects=[MockEffect("e_tooling_done", "yes")],
    )

    result = partial_order_plan(
        current_state={
            "module_c": "uninstalled",
            "module_e": "uninstalled",
            "module_c_slot": "open",
            "module_e_slot": "open",
            "c_tooling_done": "no",
            "e_tooling_done": "no",
        },
        target_state={
            "module_c": "installed",
            "module_e": "installed",
            "module_c_slot": "closed",
            "module_e_slot": "closed",
            "c_tooling_done": "yes",
            "e_tooling_done": "yes",
        },
        rules=[install_c, install_e, use_c_slot, use_e_slot],
        feature_defs={},
    )

    assert result.status == "success"
    positions = _code_positions(result)
    assert positions["OP_USE_C_SLOT"] < positions["OP_INSTALL_C"]
    assert positions["OP_USE_E_SLOT"] < positions["OP_INSTALL_E"]
    assert result.diagnostics["initial_window_ordering_count"] == 2


def test_pop_prefers_initial_window_ordering_over_reprovider_rework():
    install_a = MockRule(
        id=1,
        code="OP_INSTALL_A",
        duration_min=10,
        effects=[MockEffect("module_a", "installed")],
    )
    install_c = MockRule(
        id=2,
        code="OP_INSTALL_C",
        duration_min=10,
        preconditions=[
            MockPrecond("module_a", "eq", "installed"),
            MockPrecond("fixture_b", "eq", "uninstalled"),
        ],
        effects=[MockEffect("module_c", "installed")],
    )
    install_fixture_b = MockRule(
        id=3,
        code="OP_INSTALL_FIXTURE_B",
        duration_min=10,
        preconditions=[
            MockPrecond("fixture_b", "eq", "uninstalled"),
            MockPrecond("module_c", "eq", "uninstalled"),
        ],
        effects=[MockEffect("fixture_b", "installed")],
    )
    install_b = MockRule(
        id=4,
        code="OP_INSTALL_B",
        duration_min=10,
        preconditions=[
            MockPrecond("module_a", "eq", "installed"),
            MockPrecond("fixture_b", "eq", "installed"),
        ],
        effects=[MockEffect("module_b", "installed")],
    )
    remove_fixture_b = MockRule(
        id=5,
        code="OP_REMOVE_FIXTURE_B",
        duration_min=10,
        preconditions=[MockPrecond("fixture_b", "eq", "installed")],
        effects=[MockEffect("fixture_b", "uninstalled")],
    )
    remove_c = MockRule(
        id=6,
        code="OP_REMOVE_C",
        duration_min=10,
        preconditions=[MockPrecond("module_c", "eq", "installed")],
        effects=[MockEffect("module_c", "uninstalled")],
    )

    result = partial_order_plan(
        current_state={
            "module_a": "uninstalled",
            "module_b": "uninstalled",
            "module_c": "uninstalled",
            "fixture_b": "uninstalled",
        },
        target_state={
            "module_a": "installed",
            "module_b": "installed",
            "module_c": "installed",
            "fixture_b": "uninstalled",
        },
        rules=[install_a, install_c, install_fixture_b, install_b, remove_fixture_b, remove_c],
        feature_defs={},
    )

    assert result.status == "success"
    codes = [node.op_rule_code for node in result.nodes]
    assert "OP_REMOVE_C" not in codes
    positions = _code_positions(result)
    assert positions["OP_INSTALL_FIXTURE_B"] < positions["OP_INSTALL_C"]


def test_pop_initial_window_ordering_falls_back_when_it_would_cycle():
    breaker = MockRule(
        id=1,
        code="OP_BREAK_WINDOW",
        duration_min=10,
        preconditions=[MockPrecond("setup", "eq", "done")],
        effects=[
            MockEffect("window", "closed"),
            MockEffect("support", "ready"),
        ],
    )
    consumer = MockRule(
        id=2,
        code="OP_CONSUME_WINDOW",
        duration_min=10,
        preconditions=[
            MockPrecond("window", "eq", "open"),
            MockPrecond("support", "eq", "ready"),
        ],
        effects=[MockEffect("goal", "done")],
    )
    setup = MockRule(
        id=3,
        code="OP_SETUP",
        duration_min=10,
        effects=[MockEffect("setup", "done")],
    )

    result = partial_order_plan(
        current_state={
            "window": "open",
            "support": "missing",
            "setup": "todo",
            "goal": "todo",
        },
        target_state={
            "window": "open",
            "support": "missing",
            "setup": "todo",
            "goal": "done",
        },
        rules=[breaker, consumer, setup],
        feature_defs={},
    )

    assert result.status == "no_solution"
    assert result.diagnostics["initial_window_ordering_count"] == 0
