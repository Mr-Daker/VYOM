"""add grouping tables

Revision ID: 002_add_grouping_tables
Revises: 001_initial_schema
Create Date: 2026-09-17 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '002_add_grouping_tables'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create LearningGroup table
    op.create_table('learning_groups',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('group_type', sa.String(), nullable=False),
        sa.Column('focus_competency_id', sa.UUID(), nullable=True),
        sa.Column('check_mode', sa.String(), nullable=True),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('mixed_needs', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('teacher_modified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['focus_competency_id'], ['competencies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['session_id'], ['class_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create GroupMembership table
    op.create_table('group_memberships',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('session_id', sa.UUID(), nullable=False),
        sa.Column('group_id', sa.UUID(), nullable=False),
        sa.Column('student_id', sa.UUID(), nullable=False),
        sa.Column('focus_competency_id', sa.UUID(), nullable=True),
        sa.Column('assignment_reason', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['focus_competency_id'], ['competencies.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['group_id'], ['learning_groups.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['class_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_id', 'student_id', name='uq_membership_group_student'),
        sa.UniqueConstraint('session_id', 'student_id', name='uq_membership_session_student')
    )


def downgrade() -> None:
    op.drop_table('group_memberships')
    op.drop_table('learning_groups')
