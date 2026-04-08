"""Initial tables - all 13 tables for MVP

Revision ID: 001_initial
Revises: 
Create Date: 2026-04-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ============================================================
    # 机台与状态相关（5 张表）
    # ============================================================

    # 1. machine_type
    op.create_table(
        'machine_type',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(64), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )

    # 2. machine
    op.create_table(
        'machine',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('machine_type_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(64), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('location', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['machine_type_id'], ['machine_type.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )

    # 3. state_feature_def
    op.create_table(
        'state_feature_def',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('machine_type_id', sa.Integer(), nullable=False),
        sa.Column('feature_key', sa.String(64), nullable=False),
        sa.Column('feature_name', sa.String(128), nullable=True),
        sa.Column('value_type', sa.String(32), nullable=False),
        sa.Column('allowed_values', postgresql.JSONB(), nullable=True),
        sa.ForeignKeyConstraint(['machine_type_id'], ['machine_type.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('machine_type_id', 'feature_key')
    )

    # 4. machine_state
    op.create_table(
        'machine_state',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('machine_id', sa.Integer(), nullable=False),
        sa.Column('state_type', sa.String(32), nullable=False),
        sa.Column('label', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['machine_id'], ['machine.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 5. machine_state_feature
    op.create_table(
        'machine_state_feature',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('machine_state_id', sa.Integer(), nullable=False),
        sa.Column('feature_key', sa.String(64), nullable=False),
        sa.Column('feature_value', sa.String(256), nullable=False),
        sa.ForeignKeyConstraint(['machine_state_id'], ['machine_state.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('machine_state_id', 'feature_key')
    )

    # ============================================================
    # 工序规则相关（4 张表）
    # ============================================================

    # 6. op_rule
    op.create_table(
        'op_rule',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('machine_type_id', sa.Integer(), nullable=False),
        sa.Column('code', sa.String(64), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('duration_min', sa.Integer(), nullable=False, server_default='30'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['machine_type_id'], ['machine_type.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )

    # 7. op_rule_precond
    op.create_table(
        'op_rule_precond',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('op_rule_id', sa.Integer(), nullable=False),
        sa.Column('feature_key', sa.String(64), nullable=False),
        sa.Column('operator', sa.String(16), nullable=False, server_default='eq'),
        sa.Column('feature_value', sa.String(256), nullable=False),
        sa.ForeignKeyConstraint(['op_rule_id'], ['op_rule.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_op_rule_precond_op_rule_id', 'op_rule_precond', ['op_rule_id'])

    # 8. op_rule_effect
    op.create_table(
        'op_rule_effect',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('op_rule_id', sa.Integer(), nullable=False),
        sa.Column('feature_key', sa.String(64), nullable=False),
        sa.Column('new_value', sa.String(256), nullable=False),
        sa.ForeignKeyConstraint(['op_rule_id'], ['op_rule.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_op_rule_effect_op_rule_id', 'op_rule_effect', ['op_rule_id'])
    op.create_index('idx_op_rule_effect_feature_key', 'op_rule_effect', ['feature_key'])

    # 9. op_rule_resource_req
    op.create_table(
        'op_rule_resource_req',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('op_rule_id', sa.Integer(), nullable=False),
        sa.Column('resource_type', sa.String(64), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_required', sa.Boolean(), nullable=False, server_default='true'),
        sa.ForeignKeyConstraint(['op_rule_id'], ['op_rule.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_op_rule_resource_req_op_rule_id', 'op_rule_resource_req', ['op_rule_id'])

    # ============================================================
    # 资源相关（1 张表）
    # ============================================================

    # 10. resource
    op.create_table(
        'resource',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(64), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('resource_type', sa.String(64), nullable=False),
        sa.Column('capacity', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('is_available', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('meta', postgresql.JSONB(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    op.create_index('idx_resource_resource_type', 'resource', ['resource_type'])

    # ============================================================
    # 求解请求相关（1 张表）
    # ============================================================

    # 11. solve_request
    op.create_table(
        'solve_request',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('machine_id', sa.Integer(), nullable=False),
        sa.Column('current_state_id', sa.Integer(), nullable=False),
        sa.Column('target_state_id', sa.Integer(), nullable=False),
        sa.Column('objective', sa.String(64), nullable=False, server_default='minimize_makespan'),
        sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
        sa.Column('overrides', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('solved_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['machine_id'], ['machine.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['current_state_id'], ['machine_state.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['target_state_id'], ['machine_state.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_solve_request_status', 'solve_request', ['status'])

    # ============================================================
    # 结果相关（2 张表）
    # ============================================================

    # 12. candidate_plan
    op.create_table(
        'candidate_plan',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('solve_request_id', sa.Integer(), nullable=False),
        sa.Column('total_steps', sa.Integer(), nullable=True),
        sa.Column('search_method', sa.String(32), nullable=False, server_default='state_inference'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['solve_request_id'], ['solve_request.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # 13. candidate_plan_step
    op.create_table(
        'candidate_plan_step',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('candidate_plan_id', sa.Integer(), nullable=False),
        sa.Column('step_order', sa.Integer(), nullable=False),
        sa.Column('op_rule_id', sa.Integer(), nullable=False),
        sa.Column('predecessor_ids', postgresql.ARRAY(sa.Integer()), nullable=True, server_default='{}'),
        sa.ForeignKeyConstraint(['candidate_plan_id'], ['candidate_plan.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['op_rule_id'], ['op_rule.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('candidate_plan_id', 'step_order')
    )
    op.create_index('idx_candidate_plan_step_candidate_plan_id', 'candidate_plan_step', ['candidate_plan_id'])

    # 14. schedule_result
    op.create_table(
        'schedule_result',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('solve_request_id', sa.Integer(), nullable=False),
        sa.Column('candidate_plan_id', sa.Integer(), nullable=False),
        sa.Column('makespan', sa.Integer(), nullable=True),
        sa.Column('solver_status', sa.String(32), nullable=True),
        sa.Column('tasks', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['solve_request_id'], ['solve_request.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['candidate_plan_id'], ['candidate_plan.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    # Drop tables in reverse order
    op.drop_table('schedule_result')
    op.drop_index('idx_candidate_plan_step_candidate_plan_id', table_name='candidate_plan_step')
    op.drop_table('candidate_plan_step')
    op.drop_table('candidate_plan')
    op.drop_index('idx_solve_request_status', table_name='solve_request')
    op.drop_table('solve_request')
    op.drop_index('idx_resource_resource_type', table_name='resource')
    op.drop_table('resource')
    op.drop_index('idx_op_rule_resource_req_op_rule_id', table_name='op_rule_resource_req')
    op.drop_table('op_rule_resource_req')
    op.drop_index('idx_op_rule_effect_feature_key', table_name='op_rule_effect')
    op.drop_index('idx_op_rule_effect_op_rule_id', table_name='op_rule_effect')
    op.drop_table('op_rule_effect')
    op.drop_index('idx_op_rule_precond_op_rule_id', table_name='op_rule_precond')
    op.drop_table('op_rule_precond')
    op.drop_table('op_rule')
    op.drop_table('machine_state_feature')
    op.drop_table('machine_state')
    op.drop_table('state_feature_def')
    op.drop_table('machine')
    op.drop_table('machine_type')
