"""Canonical domain semantics shared by APIs, projections, and solvers.

The helpers deliberately use structural attributes instead of ORM types.  This
keeps the domain layer independent from persistence while allowing callers to
pass ORM entities, schema objects, dictionaries, or small test doubles.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


STATE_TRANSITION_VIEW = "state_transition"

_STATE_KINDS = frozenset({"aggregate", "atomic", "external", "manual"})
_GRAPH_ENTITY_KINDS = frozenset({"state_node", "activity_node", "atomic_activity"})


def _value(subject: Any, name: str, default: Any = None) -> Any:
    if isinstance(subject, Mapping):
        return subject.get(name, default)
    return getattr(subject, name, default)


def _normalized_state_kind(subject: Any) -> str | None:
    raw = _value(subject, "state_kind")
    if raw is None:
        return None
    normalized = str(raw).strip().lower()
    return normalized or None


def is_state_package(subject: Any) -> bool:
    """Return whether a state body is a management/aggregation package.

    Historical rows created before ``state_kind`` was consistently populated
    are read-compatible only when they do not carry an executable fact.
    """

    state_kind = _normalized_state_kind(subject)
    if state_kind is not None:
        return state_kind == "aggregate"
    return not _value(subject, "feature_key") and _value(subject, "target_value") is None


def is_atomic_state(subject: Any) -> bool:
    """Return whether a state body represents a canonical fact.

    ``atomic``, ``external``, and ``manual`` are all fact-bearing leaf
    semantics.  Their origin differs, but all three are canonical state bodies.
    """

    state_kind = _normalized_state_kind(subject)
    if state_kind is not None:
        return state_kind in {"atomic", "external", "manual"}
    return bool(_value(subject, "feature_key")) and _value(subject, "target_value") is not None


def state_semantic_warnings(subject: Any) -> tuple[str, ...]:
    """Return stable audit warning codes for legacy or inconsistent state rows."""

    state_kind = _normalized_state_kind(subject)
    has_feature = bool(_value(subject, "feature_key"))
    has_target = _value(subject, "target_value") is not None
    warnings: list[str] = []
    if state_kind is None:
        warnings.append("LEGACY_STATE_KIND_MISSING")
    elif state_kind not in _STATE_KINDS:
        warnings.append("UNKNOWN_STATE_KIND")
    if state_kind == "aggregate" and (has_feature or has_target):
        warnings.append("STATE_PACKAGE_HAS_FACT_FIELDS")
    if state_kind in {"atomic", "external", "manual"} and not (has_feature and has_target):
        warnings.append("ATOMIC_STATE_FACT_INCOMPLETE")
    if state_kind is None and has_feature != has_target:
        warnings.append("LEGACY_STATE_FACT_INCOMPLETE")
    return tuple(warnings)


def is_activity_package(subject: Any) -> bool:
    """Return whether an activity node is a pure management package."""

    return _value(subject, "level") in {1, 2}


def is_legacy_executable_activity(subject: Any) -> bool:
    """Return whether an ActivityNode is a retired level-3 executable row."""

    return _value(subject, "level") == 3


@dataclass(frozen=True, slots=True)
class GraphIdentity:
    """Parsed graph identity with separate canonical body and display reference."""

    entity_kind: str
    canonical_id: int
    reference_id: int | None = None
    draft_id: str | None = None

    @property
    def is_reference(self) -> bool:
        return self.reference_id is not None

    @property
    def is_draft(self) -> bool:
        return self.draft_id is not None


def _positive_id(value: int, field: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return parsed


def state_graph_id(state_node_id: int) -> str:
    return f"state_node:{_positive_id(state_node_id, 'state_node_id')}"


def state_reference_graph_id(state_node_id: int, reference_id: int) -> str:
    return (
        f"{state_graph_id(state_node_id)}:"
        f"ref:{_positive_id(reference_id, 'reference_id')}"
    )


def activity_graph_id(activity_node_id: int) -> str:
    return f"activity_node:{_positive_id(activity_node_id, 'activity_node_id')}"


def atomic_activity_graph_id(atomic_activity_id: int) -> str:
    return f"atomic_activity:{_positive_id(atomic_activity_id, 'atomic_activity_id')}"


def activity_reference_graph_id(atomic_activity_id: int, reference_id: int) -> str:
    return (
        f"{atomic_activity_graph_id(atomic_activity_id)}:"
        f"ref:{_positive_id(reference_id, 'reference_id')}"
    )


def parse_graph_id(graph_id: str) -> GraphIdentity:
    """Parse canonical, reference-instance, and draft graph IDs.

    Supported forms are ``kind:id``, ``kind:id:ref:id`` and
    ``draft-kind:opaque-id``.  Unknown or malformed forms fail closed.
    """

    raw = str(graph_id or "").strip()
    parts = raw.split(":")
    if len(parts) == 2 and parts[0] in _GRAPH_ENTITY_KINDS:
        return GraphIdentity(parts[0], _positive_id(int(parts[1]), "canonical_id"))
    if (
        len(parts) == 4
        and parts[0] in {"state_node", "atomic_activity"}
        and parts[2] == "ref"
    ):
        return GraphIdentity(
            parts[0],
            _positive_id(int(parts[1]), "canonical_id"),
            reference_id=_positive_id(int(parts[3]), "reference_id"),
        )
    if len(parts) >= 2 and parts[0].startswith("draft-"):
        entity_kind = parts[0][len("draft-") :]
        if entity_kind not in _GRAPH_ENTITY_KINDS:
            raise ValueError(f"Unsupported draft graph entity kind: {entity_kind}")
        draft_id = ":".join(parts[1:]).strip()
        if not draft_id:
            raise ValueError("draft_id must not be empty")
        return GraphIdentity(entity_kind, 0, draft_id=draft_id)
    raise ValueError(f"Unsupported graph ID: {graph_id!r}")


def canonical_graph_id(graph_id: str) -> str:
    """Return the canonical body graph ID for a display graph ID."""

    identity = parse_graph_id(graph_id)
    if identity.is_draft:
        return graph_id
    if identity.entity_kind == "state_node":
        return state_graph_id(identity.canonical_id)
    if identity.entity_kind == "activity_node":
        return activity_graph_id(identity.canonical_id)
    return atomic_activity_graph_id(identity.canonical_id)
