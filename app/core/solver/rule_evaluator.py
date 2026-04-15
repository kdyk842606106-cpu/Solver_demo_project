"""
RuleEvaluator: unified entry point for all precondition matching and effect application.

Strategy pattern: all precond matching and effect application MUST go through this class.
No if/elif dispatch allowed in this module.
"""

from app.core.planner.state import StateDict
from app.core.solver.operators import OperatorRegistry
from app.core.solver.effects import EffectRegistry
from app.db.models import OpRulePrecond, OpRuleEffect


class RuleEvaluator:
    """
    Unified rule evaluation engine.

    All precondition matching and effect application MUST use this class.
    Type-safe: numeric comparison failures return False, not exceptions.
    """

    def evaluate_precondition(
        self,
        state: StateDict,
        precond: OpRulePrecond,
    ) -> bool:
        """
        Check if state satisfies a single precondition.

        Delegates to OperatorRegistry for actual comparison.
        Type-safe: numeric comparisons that fail return False.

        Args:
            state: Current state dictionary
            precond: OpRulePrecond ORM object

        Returns:
            bool: True if precondition is satisfied
        """
        current = state.get(precond.feature_key)
        if current is None:
            return False
        return OperatorRegistry.evaluate_precond(
            current_value=current,
            operator_name=precond.operator,
            feature_value=precond.feature_value,
            value_list=getattr(precond, 'value_list', None),
        )

    def evaluate_preconditions(
        self,
        state: StateDict,
        preconditions: list[OpRulePrecond],
    ) -> bool:
        """
        Check if state satisfies ALL preconditions.

        Args:
            state: Current state dictionary
            preconditions: List of OpRulePrecond ORM objects

        Returns:
            bool: True only if ALL preconditions are satisfied
        """
        return all(self.evaluate_precondition(state, p) for p in preconditions)

    def apply_effect(self, state: StateDict, effect: OpRuleEffect) -> StateDict:
        """
        Apply a single effect to state, returning a NEW state copy.

        Does NOT mutate the input state object.

        Args:
            state: Current state dictionary
            effect: OpRuleEffect ORM object

        Returns:
            StateDict: New state with effect applied
        """
        new_state = dict(state)
        effect_type = getattr(effect, 'effect_type', 'set')

        new_value = EffectRegistry.apply(
            current_value=state.get(effect.feature_key),
            new_value=getattr(effect, 'new_value', None),
            effect_type=effect_type,
            delta_value=getattr(effect, 'delta_value', None),
        )

        new_state[effect.feature_key] = new_value
        return new_state

    def apply_effects(
        self,
        state: StateDict,
        effects: list[OpRuleEffect],
    ) -> StateDict:
        """
        Apply multiple effects to state sequentially, returning final new state.

        Args:
            state: Current state dictionary
            effects: List of OpRuleEffect ORM objects

        Returns:
            StateDict: New state after all effects applied
        """
        result = dict(state)
        for e in effects:
            result = self.apply_effect(result, e)
        return result
