"""
State representation and manipulation module.

This module provides functions for:
- Loading machine state from database
- Computing state differences (delta)
- Checking if goal state is reached
- State hashing for deduplication
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MachineState, MachineStateFeature


# Type alias for state representation
StateDict = dict[str, str]


async def load_state(state_id: int, session: AsyncSession) -> Optional[StateDict]:
    """
    Load a machine state from database as a key-value dictionary.

    Args:
        state_id: ID of the machine_state record
        session: SQLAlchemy async session

    Returns:
        Dictionary mapping feature_key to feature_value, or None if not found
    """
    result = await session.execute(
        select(MachineStateFeature)
        .where(MachineStateFeature.machine_state_id == state_id)
    )
    features = result.scalars().all()

    if not features:
        return None

    return {f.feature_key: f.feature_value for f in features}


async def load_state_with_label(
    state_id: int, session: AsyncSession
) -> Optional[tuple[StateDict, str]]:
    """
    Load a machine state with its label.

    Args:
        state_id: ID of the machine_state record
        session: SQLAlchemy async session

    Returns:
        Tuple of (state_dict, label) or None if not found
    """
    result = await session.execute(
        select(MachineState).where(MachineState.id == state_id)
    )
    state = result.scalar_one_or_none()

    if state is None:
        return None

    state_dict = await load_state(state_id, session)
    if state_dict is None:
        return None

    return state_dict, state.label or ""


def compute_state_delta(current: StateDict, target: StateDict) -> dict[str, tuple[str, str]]:
    """
    Compute the difference between current and target states.

    This identifies which features need to change to reach the target state.

    Args:
        current: Current state dictionary
        target: Target state dictionary

    Returns:
        Dictionary mapping feature_key to (current_value, target_value) for features
        that differ between current and target states.

    Example:
        >>> current = {"temperature": "cold", "clean": "dirty"}
        >>> target = {"temperature": "hot", "clean": "clean"}
        >>> compute_state_delta(current, target)
        {"temperature": ("cold", "hot"), "clean": ("dirty", "clean")}
    """
    delta = {}

    for key, target_value in target.items():
        current_value = current.get(key)
        if current_value != target_value:
            delta[key] = (current_value or "", target_value)

    return delta


def is_goal(current: StateDict, target: StateDict) -> bool:
    """
    Check if current state matches target state.

    Args:
        current: Current state dictionary
        target: Target state dictionary

    Returns:
        True if all target features match current state
    """
    return compute_state_delta(current, target) == {}


def freeze(state: StateDict) -> frozenset:
    """
    Convert state to a hashable frozenset for deduplication.

    Used in BFS/A* search to track visited states.

    Args:
        state: State dictionary

    Returns:
        Frozenset of (key, value) tuples
    """
    return frozenset(state.items())


def unfreeze(frozen: frozenset) -> StateDict:
    """
    Convert frozen state back to dictionary.

    Args:
        frozen: Frozenset of (key, value) tuples

    Returns:
        State dictionary
    """
    return dict(frozen)


def state_matches_precondition(
    state: StateDict,
    feature_key: str,
    operator: str,
    feature_value: str,
    value_list: list | None = None,
) -> bool:
    """
    Check if a state satisfies a single precondition.

    Delegates to OperatorRegistry for type-safe comparison.
    gte/lte/in operators are now supported via the registry.
    """
    from app.core.solver.operators import OperatorRegistry

    current_value = state.get(feature_key)

    if current_value is None:
        return False

    return OperatorRegistry.evaluate_precond(
        current_value=current_value,
        operator_name=operator,
        feature_value=feature_value,
        value_list=value_list,
    )


def format_state(state: StateDict) -> str:
    """
    Format state as a readable string.

    Args:
        state: State dictionary

    Returns:
        Human-readable string representation
    """
    if not state:
        return "{}"

    items = ", ".join(f"{k}={v}" for k, v in sorted(state.items()))
    return f"{{{items}}}"
