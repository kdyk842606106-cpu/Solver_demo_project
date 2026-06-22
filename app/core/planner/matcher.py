"""
Operation rule matching module.

This module provides functions for:
- Loading operation rules from database
- Checking if state satisfies preconditions (forward matching)
- Finding operations that can produce a target effect (effect matching)
- Finding operations that can satisfy a precondition (backward matching)
"""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import OpRule, OpRuleEffect, OpRulePrecond
from app.core.planner.state import StateDict, state_matches_precondition
from app.core.solver.rule_evaluator import RuleEvaluator


async def load_rules(
    machine_type_id: int,
    session: AsyncSession,
    active_only: bool = True,
    include_repair: bool = False,
) -> list[OpRule]:
    """
    Load all operation rules for a machine type.
    
    Args:
        machine_type_id: ID of the machine type
        session: SQLAlchemy async session
        active_only: If True, only load active rules
        
    Returns:
        List of OpRule objects with preconditions, effects, and resource requirements loaded
    """
    query = (
        select(OpRule)
        .where(OpRule.machine_type_id == machine_type_id)
        .options(
            selectinload(OpRule.preconditions),
            selectinload(OpRule.effects),
            selectinload(OpRule.resource_reqs),
        )
    )

    if active_only:
        query = query.where(OpRule.is_active == True)
        if not include_repair:
            query = query.where(OpRule.is_repair == False)

    result = await session.execute(query)
    return list(result.scalars().all())


def check_preconditions(state: StateDict, preconditions: list[OpRulePrecond]) -> bool:
    """
    Check if a state satisfies all preconditions.

    Forward matching: given a state and a list of preconditions,
    determine if the state satisfies all of them.

    Delegates to RuleEvaluator for type-safe evaluation.

    Args:
        state: Current state dictionary
        preconditions: List of OpRulePrecond objects

    Returns:
        True if all preconditions are satisfied
    """
    if not preconditions:
        return True

    evaluator = RuleEvaluator()
    return evaluator.evaluate_preconditions(state, preconditions)


def find_ops_for_delta(
    feature_key: str,
    target_value: str,
    rules: list[OpRule],
    current_state: StateDict | None = None,
) -> list[OpRule]:
    """
    Find operations that can produce a specific effect.
    
    Effect matching: given a feature key and target value,
    find all operations whose effects include that transformation.
    
    For set/reset effects: checks if effect.new_value == target_value
    For increment/decrement/sub effects: simulates applying the effect to
    current_state and checks if result matches target_value.
    
    Args:
        feature_key: Feature key to change
        target_value: Target value for the feature
        rules: List of OpRule objects to search
        current_state: Current state dict for simulating increment/decrement/sub
        
    Returns:
        List of OpRule objects that can produce the target effect
    """
    matching_ops = []
    evaluator = RuleEvaluator()
    
    for rule in rules:
        for effect in rule.effects:
            if effect.feature_key != feature_key:
                continue
            
            effect_type = getattr(effect, 'effect_type', 'set')
            
            if effect_type in {'set', 'reset'}:
                if effect.new_value == target_value:
                    matching_ops.append(rule)
                    break
            else:
                if current_state is not None:
                    current_val = current_state.get(feature_key)
                    result = evaluator.apply_effect(current_state, effect)
                    if result.get(feature_key) == target_value:
                        matching_ops.append(rule)
                        break
    
    return matching_ops


def find_provider(
    feature_key: str,
    required_value: str,
    candidates: list[OpRule],
    exclude: Optional[OpRule] = None,
    current_state: StateDict | None = None,
) -> Optional[OpRule]:
    """
    Find an operation that can satisfy a precondition.
    
    Backward matching: given a precondition (feature_key + required_value),
    find an operation among candidates whose effects can satisfy it.
    
    When multiple candidates can satisfy the precondition, select the one
    with the shortest duration (optimal selection for RAG construction).
    
    Args:
        feature_key: Feature key required by precondition
        required_value: Value required by precondition
        candidates: List of candidate OpRule objects
        exclude: Optional OpRule to exclude from consideration
        current_state: Current state dict for simulating increment/decrement/sub
        
    Returns:
        Best OpRule that can satisfy the precondition, or None if not found
    """
    providers = []
    evaluator = RuleEvaluator()
    
    for rule in candidates:
        if exclude and rule.id == exclude.id:
            continue
        
        for effect in rule.effects:
            if effect.feature_key != feature_key:
                continue
            
            effect_type = getattr(effect, 'effect_type', 'set')
            
            if effect_type in {'set', 'reset'}:
                if effect.new_value == required_value:
                    providers.append(rule)
                    break
            else:
                if current_state is not None:
                    current_val = current_state.get(feature_key)
                    result = evaluator.apply_effect(current_state, effect)
                    if result.get(feature_key) == required_value:
                        providers.append(rule)
                        break
    
    if not providers:
        return None
    
    # Select the one with shortest duration (optimal)
    return min(providers, key=lambda r: r.duration_min)


def get_precondition_dict(preconditions: list[OpRulePrecond]) -> dict[str, tuple[str, str]]:
    """
    Convert preconditions list to dictionary format.
    
    Args:
        preconditions: List of OpRulePrecond objects
        
    Returns:
        Dictionary mapping feature_key to (operator, value)
    """
    return {p.feature_key: (p.operator, p.feature_value) for p in preconditions}


def get_effect_dict(effects: list[OpRuleEffect]) -> dict[str, str]:
    """
    Convert effects list to dictionary format.
    
    Args:
        effects: List of OpRuleEffect objects
        
    Returns:
        Dictionary mapping feature_key to new_value
    """
    return {e.feature_key: e.new_value for e in effects}


def rule_summary(rule: OpRule) -> str:
    """
    Generate a human-readable summary of an operation rule.
    
    Args:
        rule: OpRule object
        
    Returns:
        Summary string
    """
    preconds = ", ".join(
        f"{p.feature_key}={p.feature_value}" 
        for p in rule.preconditions
    ) or "none"
    
    effects = ", ".join(
        f"{e.feature_key}→{e.new_value}" 
        for e in rule.effects
    ) or "none"
    
    return f"{rule.code}({rule.duration_min}min): [{preconds}] → [{effects}]"
