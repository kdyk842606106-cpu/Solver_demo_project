"""Merge the retired knowledge marker with Planner scenario storage.

Revision ID: 016_planner_compat_merge
Revises: 015_knowledge_repository, 015_planner_scenario
Create Date: 2026-08-25
"""

from typing import Sequence, Union


revision: str = "016_planner_compat_merge"
down_revision: Union[str, Sequence[str], None] = (
    "015_knowledge_repository",
    "015_planner_scenario",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
