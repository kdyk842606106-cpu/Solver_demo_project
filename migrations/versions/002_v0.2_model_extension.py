"""V0.2 model extensions - feature_definition, blockage_event, new fields

Revision ID: 002_v0.2_model_extension
Revises: 001_initial
Create Date: 2026-04-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_v0.2_model_extension'
down_revision: Union[str, None] = '001_initial'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # 1. feature_definition: 特征类型系统（新增表）
    # ============================================================
    op.create_table(
        'feature_definition',
        sa.Column('feature_key', sa.String(64), nullable=False),
        sa.Column('value_type', sa.String(32), nullable=False),
        sa.Column('allowed_values', postgresql.JSONB(), nullable=True),
        sa.Column('unit', sa.String(32), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('feature_key')
    )

    # ============================================================
    # 2. op_rule_precond: 新增字段
    # ============================================================
    op.add_column('op_rule_precond', sa.Column('value_list', postgresql.JSONB(), nullable=True))

    # ============================================================
    # 3. op_rule_effect: 新增字段
    # ============================================================
    op.add_column('op_rule_effect', sa.Column('effect_type', sa.String(32), nullable=False, server_default='set'))
    op.add_column('op_rule_effect', sa.Column('delta_value', sa.Numeric(10, 2), nullable=True))

    # ============================================================
    # 4. op_rule: 新增字段
    # ============================================================
    op.add_column('op_rule', sa.Column('is_repair', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('op_rule', sa.Column('valid_from', sa.DateTime(timezone=True), nullable=True))
    op.add_column('op_rule', sa.Column('valid_to', sa.DateTime(timezone=True), nullable=True))

    # ============================================================
    # 5. solve_request: 新增字段
    # ============================================================
    op.add_column('solve_request', sa.Column('objectives', postgresql.JSONB(), nullable=True, server_default='[{"type":"minimize_makespan","weight":1.0}]'))
    op.add_column('solve_request', sa.Column('constraints', postgresql.JSONB(), nullable=True, server_default='{}'))
    op.add_column('solve_request', sa.Column('parent_plan_id', sa.Integer(), nullable=True))

    # ============================================================
    # 6. candidate_plan: 新增字段
    # ============================================================
    op.add_column('candidate_plan', sa.Column('version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('candidate_plan', sa.Column('parent_plan_id', sa.Integer(), nullable=True))
    op.add_column('candidate_plan', sa.Column('replan_reason', sa.String(64), nullable=True))
    op.add_column('candidate_plan', sa.Column('status', sa.String(32), nullable=False, server_default='draft'))
    op.create_foreign_key('fk_candidate_plan_parent', 'candidate_plan', 'candidate_plan', ['parent_plan_id'], ['id'])

    # ============================================================
    # 7. candidate_plan_step: 新增字段
    # ============================================================
    op.add_column('candidate_plan_step', sa.Column('not_before', sa.Integer(), nullable=True))
    op.add_column('candidate_plan_step', sa.Column('step_role', sa.String(32), nullable=False, server_default='normal'))

    # ============================================================
    # 8. blockage_event: 阻塞事件表（新增表）
    # ============================================================
    op.create_table(
        'blockage_event',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('plan_id', sa.Integer(), nullable=False),
        sa.Column('blocked_step_id', sa.Integer(), nullable=False),
        sa.Column('strategy', sa.String(8), nullable=False),
        sa.Column('not_before_offset', sa.Integer(), nullable=True),
        sa.Column('blockage_reason', sa.String(64), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('created_by', sa.String(64), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['candidate_plan.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['blocked_step_id'], ['candidate_plan_step.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_blockage_event_plan_id', 'blockage_event', ['plan_id'])

    # ============================================================
    # 9. Add foreign key for solve_request.parent_plan_id
    # ============================================================
    op.create_foreign_key('fk_solve_request_parent_plan', 'solve_request', 'candidate_plan', ['parent_plan_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_solve_request_parent_plan', 'solve_request', type_='foreignkey')
    op.drop_index('idx_blockage_event_plan_id', table_name='blockage_event')
    op.drop_table('blockage_event')
    op.drop_column('candidate_plan_step', 'step_role')
    op.drop_column('candidate_plan_step', 'not_before')
    op.drop_constraint('fk_candidate_plan_parent', 'candidate_plan', type_='foreignkey')
    op.drop_column('candidate_plan', 'status')
    op.drop_column('candidate_plan', 'replan_reason')
    op.drop_column('candidate_plan', 'parent_plan_id')
    op.drop_column('candidate_plan', 'version')
    op.drop_column('solve_request', 'parent_plan_id')
    op.drop_column('solve_request', 'constraints')
    op.drop_column('solve_request', 'objectives')
    op.drop_column('op_rule', 'valid_to')
    op.drop_column('op_rule', 'valid_from')
    op.drop_column('op_rule', 'is_repair')
    op.drop_column('op_rule_effect', 'delta_value')
    op.drop_column('op_rule_effect', 'effect_type')
    op.drop_column('op_rule_precond', 'value_list')
    op.drop_table('feature_definition')