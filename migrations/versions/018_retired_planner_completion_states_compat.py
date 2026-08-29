"""Recognize databases stamped by the retired completion-state migration.

Revision ID: 018_planner_completion_states
Revises: 017_planner_runtime_state_targets
Create Date: 2026-08-28

The completion-state model was removed before release, but some local verifier
databases were already stamped with its revision.  Keep this no-op marker so
Alembic can load those databases without restoring the retired data migration.
"""

from typing import Sequence, Union


revision: str = "018_planner_completion_states"
down_revision: Union[str, None] = "017_planner_runtime_state_targets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
