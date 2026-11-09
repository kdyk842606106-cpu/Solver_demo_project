"""Disabling strengthening preserves the existing business model."""
from tests.unit.test_joint_cpsat import core, setup_db
from tests.unit.test_joint_mandatory import repair_case


def test_disabled_skips_detector_and_adds_no_rank_or_mandatory_constraints(core, monkeypatch):
    monkeypatch.setattr(core, '_MANDATORY_ENCODING', 'none')
    monkeypatch.setattr(core, '_CAUSAL_RANKS', False)
    def unexpected(*args, **kwargs):
        raise AssertionError('Mandatory detector must not run when disabled')
    monkeypatch.setattr(core, 'identify_mandatory_activities', unexpected)
    model, _, slots, stats, _ = core._build_model_with_finish(repair_case(), deadline=None)
    assert slots and all(not s.mandatory and s.causal_rank is None for s in slots)
    assert not any(c.name.startswith(('mandatory:', 'causal_rank:')) for c in model.proto.constraints)
    assert stats['mandatory_activities']['status'] == 'disabled'
    assert stats['mandatory_activities']['added_constraints'] == 0
    assert stats['mandatory_activities']['fixed_first_occurrences'] == 0
    assert stats['causal_ranks']['enabled'] is False


def test_disabling_mandatory_removes_only_proven_presence_equalities(core, monkeypatch):
    monkeypatch.setattr(core, '_CAUSAL_RANKS', False)
    monkeypatch.setattr(core, '_MANDATORY_ENCODING', 'appended')
    old, _, old_slots, old_stats, _ = core._build_model_with_finish(repair_case(), deadline=None)
    monkeypatch.setattr(core, '_MANDATORY_ENCODING', 'none')
    new, _, slots, stats, _ = core._build_model_with_finish(repair_case(), deadline=None)
    assert [str(v) for v in old.proto.variables] == [str(v) for v in new.proto.variables]
    assert [str(c) for c in old.proto.constraints if not c.name.startswith('mandatory:')] == [str(c) for c in new.proto.constraints]
    assert str(old.proto.objective) == str(new.proto.objective)
    assert str(old.proto.solution_hint) == str(new.proto.solution_hint)
    assert [(s.aid, s.ordinal) for s in old_slots] == [(s.aid, s.ordinal) for s in slots]
    assert len(old.proto.constraints)-len(new.proto.constraints) == 4
    for key in ('optional_occurrence_slots', 'support_choices', 'threat_checks', 'interval_locks', 'horizon'):
        assert old_stats[key] == stats[key]
