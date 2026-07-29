import pytest

from scripts.check_scope_guard_zero import validate_scope_guard_counts


def test_scope_guard_zero_gate_accepts_empty_tables():
    validate_scope_guard_counts(0, 0)


@pytest.mark.parametrize("guard_count,precondition_count", [(1, 0), (0, 1), (2, 3)])
def test_scope_guard_zero_gate_blocks_nonzero_without_conversion(
    guard_count,
    precondition_count,
):
    with pytest.raises(RuntimeError, match="SCOPE_GUARD_DATA_PRESENT"):
        validate_scope_guard_counts(guard_count, precondition_count)
