from types import SimpleNamespace

import pytest

from app.core.modeling.semantics import (
    STATE_TRANSITION_VIEW,
    activity_graph_id,
    activity_reference_graph_id,
    atomic_activity_graph_id,
    canonical_graph_id,
    is_activity_package,
    is_atomic_state,
    is_legacy_executable_activity,
    is_state_package,
    parse_graph_id,
    state_graph_id,
    state_reference_graph_id,
    state_semantic_warnings,
)


@pytest.mark.parametrize("state_kind", ["atomic", "external", "manual"])
def test_fact_bearing_state_kinds_are_atomic_states(state_kind):
    state = SimpleNamespace(
        state_kind=state_kind,
        feature_key="phase",
        target_value="done",
    )

    assert is_atomic_state(state)
    assert not is_state_package(state)
    assert state_semantic_warnings(state) == ()


def test_aggregate_state_is_a_package():
    state = {"state_kind": "aggregate", "feature_key": None, "target_value": None}

    assert is_state_package(state)
    assert not is_atomic_state(state)


def test_legacy_missing_state_kind_is_read_compatible_and_audited():
    legacy_fact = {"feature_key": "phase", "target_value": "done"}
    legacy_package = {"feature_key": None, "target_value": None}

    assert is_atomic_state(legacy_fact)
    assert is_state_package(legacy_package)
    assert state_semantic_warnings(legacy_fact) == ("LEGACY_STATE_KIND_MISSING",)


def test_inconsistent_state_rows_keep_explicit_semantics_and_emit_warning():
    dirty_package = {
        "state_kind": "aggregate",
        "feature_key": "phase",
        "target_value": "done",
    }
    incomplete_atomic = {
        "state_kind": "atomic",
        "feature_key": "phase",
        "target_value": None,
    }

    assert is_state_package(dirty_package)
    assert is_atomic_state(incomplete_atomic)
    assert "STATE_PACKAGE_HAS_FACT_FIELDS" in state_semantic_warnings(dirty_package)
    assert "ATOMIC_STATE_FACT_INCOMPLETE" in state_semantic_warnings(incomplete_atomic)


@pytest.mark.parametrize("level", [1, 2])
def test_activity_levels_one_and_two_are_management_packages(level):
    assert is_activity_package({"level": level})
    assert not is_legacy_executable_activity({"level": level})


def test_level_three_activity_is_legacy_executable():
    assert is_legacy_executable_activity({"level": 3})
    assert not is_activity_package({"level": 3})


def test_graph_ids_round_trip_and_preserve_canonical_identity():
    state_ref_id = state_reference_graph_id(12, 34)
    activity_ref_id = activity_reference_graph_id(56, 78)

    assert state_graph_id(12) == "state_node:12"
    assert activity_graph_id(9) == "activity_node:9"
    assert atomic_activity_graph_id(56) == "atomic_activity:56"
    assert parse_graph_id(state_ref_id).canonical_id == 12
    assert parse_graph_id(state_ref_id).reference_id == 34
    assert parse_graph_id(activity_ref_id).canonical_id == 56
    assert canonical_graph_id(state_ref_id) == "state_node:12"
    assert canonical_graph_id(activity_ref_id) == "atomic_activity:56"


def test_graph_id_parser_rejects_malformed_or_unknown_identity():
    with pytest.raises(ValueError):
        parse_graph_id("state_node:not-an-id")
    with pytest.raises(ValueError):
        parse_graph_id("scope_guard:1")


def test_single_business_canvas_constant_is_state_transition():
    assert STATE_TRANSITION_VIEW == "state_transition"
