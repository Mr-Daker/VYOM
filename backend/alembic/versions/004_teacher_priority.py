"""teacher priority

Revision ID: 004_teacher_priority
Revises: 003_grouping_hardening
Create Date: 2026-09-17 12:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '004_teacher_priority'
down_revision: Union[str, None] = '003_grouping_hardening'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add metadata to ClassSession
    op.add_column('class_sessions', sa.Column('priority_generated_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('class_sessions', sa.Column('priority_stale', sa.Boolean(), server_default='false', nullable=False))

    # Create GroupPriority table
    op.create_table(
        'group_priorities',
        sa.Column('id', sa.UUID(), primary_key=True),
        sa.Column('session_id', sa.UUID(), sa.ForeignKey('class_sessions.id'), nullable=False),
        sa.Column('group_id', sa.UUID(), sa.ForeignKey('learning_groups.id', ondelete='CASCADE'), nullable=False),
        
        sa.Column('priority_score', sa.Float(), nullable=False),
        sa.Column('priority_rank', sa.Integer(), nullable=False),
        sa.Column('priority_tier', sa.String(), nullable=False),
        
        sa.Column('teacher_rank', sa.Integer(), nullable=True),
        sa.Column('teacher_override_reason', sa.String(), nullable=True),
        
        sa.Column('instructional_need_score', sa.Float(), nullable=False),
        sa.Column('evidence_severity_score', sa.Float(), nullable=False),
        sa.Column('uncertainty_score', sa.Float(), nullable=False),
        sa.Column('missed_instruction_score', sa.Float(), nullable=False),
        sa.Column('group_complexity_score', sa.Float(), nullable=False),
        sa.Column('reach_score', sa.Float(), nullable=False),
        
        sa.Column('factor_breakdown', sa.JSON(), nullable=False),
        sa.Column('reasons', sa.JSON(), nullable=False),
        sa.Column('top_reason', sa.String(), nullable=False),
        
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        
        sa.UniqueConstraint('session_id', 'group_id', name='uq_priority_session_group'),
        sa.CheckConstraint('priority_score >= 0 AND priority_score <= 100', name='chk_priority_score_range'),
        sa.CheckConstraint('priority_rank > 0', name='chk_priority_rank_positive'),
        sa.CheckConstraint('teacher_rank IS NULL OR teacher_rank > 0', name='chk_teacher_rank_positive'),
        sa.CheckConstraint('instructional_need_score >= 0', name='chk_instructional_need_positive'),
        sa.CheckConstraint('evidence_severity_score >= 0', name='chk_evidence_severity_positive'),
        sa.CheckConstraint('uncertainty_score >= 0', name='chk_uncertainty_positive'),
        sa.CheckConstraint('missed_instruction_score >= 0', name='chk_missed_instruction_positive'),
        sa.CheckConstraint('group_complexity_score >= 0', name='chk_group_complexity_positive'),
        sa.CheckConstraint('reach_score >= 0', name='chk_reach_positive'),
        sa.CheckConstraint("priority_tier IN ('urgent', 'high', 'moderate', 'low')", name='chk_priority_tier')
    )


def downgrade() -> None:
    op.drop_table('group_priorities')
    op.drop_column('class_sessions', 'priority_stale')
    op.drop_column('class_sessions', 'priority_generated_at')

