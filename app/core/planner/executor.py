"""
State transition execution module.

This module provides functions for:
- Applying operation effects to states
- Previewing effects without modifying state
"""

from typing import Any

from app.db.models import OpRule, OpRuleEffect
from app.core.planner.state import StateDict


def apply_effects(state: StateDict, effects: list[OpRuleEffect]) -> StateDict:
    """
    Apply operation effects to a state, returning a new state.
    
    This function is pure - it does not modify the input state.
    Instead, it returns a new state dictionary with the effects applied.
    
    Args:
        state: Current state dictionary
        effects: List of OpRuleEffect objects to apply
        
    Returns:
        New state dictionary with effects applied
    """
    # Create a copy of the state
    new_state = dict(state)
    
    # Apply each effect
    for effect in effects:
        new_state[effect.feature_key] = effect.new_value
    
    return new_state


def apply_rule(state: StateDict, rule: OpRule) -> StateDict:
    """
    Apply an operation rule to a state.
    
    Convenience function that applies all effects of a rule.
    
    Args:
        state: Current state dictionary
        rule: OpRule object with effects loaded
        
    Returns:
        New state dictionary with rule's effects applied
    """
    return apply_effects(state, rule.effects)


def preview_effects(effects: list[OpRuleEffect]) -> dict[str, str]:
    """
    Preview effects as a dictionary.
    
    This is useful for RAG construction to understand what
    changes an operation will make without actually applying them.
    
    Args:
        effects: List of OpRuleEffect objects
        
    Returns:
        Dictionary mapping feature_key to new_value
    """
    return {e.feature_key: e.new_value for e in effects}


def preview_rule(rule: OpRule) -> dict[str, str]:
    """
    Preview an operation rule's effects.
    
    Args:
        rule: OpRule object with effects loaded
        
    Returns:
        Dictionary mapping feature_key to new_value
    """
    return preview_effects(rule.effects)


def compute_effect_delta(
    state: StateDict, 
    effects: list[OpRuleEffect]
) -> dict[str, tuple[str, str]]:
    """
    Compute what would change if effects were applied.
    
    Args:
        state: Current state dictionary
        effects: List of OpRuleEffect objects
        
    Returns:
        Dictionary mapping feature_key to (old_value, new_value) for
        features that would change
    """
    delta = {}
    
    for effect in effects:
        old_value = state.get(effect.feature_key, "")
        if old_value != effect.new_value:
            delta[effect.feature_key] = (old_value, effect.new_value)
    
    return delta


def effects_satisfy_precondition(
    effects: list[OpRuleEffect],
    feature_key: str,
    required_value: str
) -> bool:
    """
    Check if a set of effects can satisfy a precondition.
    
    This is used in RAG construction to determine if one operation's
    effects can satisfy another operation's precondition.
    
    Args:
        effects: List of OpRuleEffect objects
        feature_key: Feature key required by precondition
        required_value: Value required by precondition
        
    Returns:
        True if effects include the required transformation
    """
    for effect in effects:
        if effect.feature_key == feature_key and effect.new_value == required_value:
            return True
    return False


def format_effects(effects: list[OpRuleEffect]) -> str:
    """
    Format effects as a readable string.
    
    Args:
        effects: List of OpRuleEffect objects
        
    Returns:
        Human-readable string representation
    """
    if not effects:
        return "none"
    
    return ", ".join(f"{e.feature_key}→{e.new_value}" for e in effects)
