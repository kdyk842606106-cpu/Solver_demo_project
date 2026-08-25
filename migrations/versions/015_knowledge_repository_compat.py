"""Recognize databases left at the retired knowledge-repository revision.

Revision ID: 015_knowledge_repository
Revises: 014_body_reference_unification
Create Date: 2026-08-25

This is deliberately a no-op compatibility marker. The Planner-only product
does not create, read, or remove knowledge-repository structures. Existing
tables are left dormant so switching editions never destroys user data.
"""

from typing import Sequence, Union


revision: str = "015_knowledge_repository"
down_revision: Union[str, None] = "014_body_reference_unification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
