import pytest

from scripts.audit_body_reference_model import BLOCKING_KEYS, validate_audit_counts


def test_body_reference_audit_accepts_zero_blockers():
    validate_audit_counts({key: 0 for key in BLOCKING_KEYS})


@pytest.mark.parametrize("key", BLOCKING_KEYS)
def test_body_reference_audit_rejects_each_blocker(key):
    with pytest.raises(RuntimeError, match=key):
        validate_audit_counts({key: 1})
