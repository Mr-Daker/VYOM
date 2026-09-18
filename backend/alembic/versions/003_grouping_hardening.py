"""grouping hardening

Revision ID: 003_grouping_hardening
Revises: 002_add_grouping_tables
Create Date: 2026-09-17 12:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '003_grouping_hardening'
down_revision: Union[str, None] = '002_add_grouping_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add metadata to ClassSession
    op.add_column('class_sessions', sa.Column('grouping_warnings', sa.JSON(), nullable=True))
    op.add_column('class_sessions', sa.Column('grouping_compressed', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('class_sessions', sa.Column('groups_teacher_modified', sa.Boolean(), server_default='false', nullable=False))

    # Add metadata to GroupMembership
    op.add_column('group_memberships', sa.Column('original_group_type', sa.String(), nullable=True))
    op.add_column('group_memberships', sa.Column('original_check_mode', sa.String(), nullable=True))
    op.add_column('group_memberships', sa.Column('teacher_override_reason', sa.String(), nullable=True))

    # Add CHECK constraints for enums
    op.create_check_constraint(
        'chk_group_type',
        'learning_groups',
        "group_type IN ('recovery', 'check', 'guided', 'practice', 'extension', 'mixed_support')"
    )
    op.create_check_constraint(
        'chk_check_mode',
        'learning_groups',
        "check_mode IS NULL OR check_mode IN ('assessment', 'quick_check')"
    )

def downgrade() -> None:
    op.drop_constraint('chk_check_mode', 'learning_groups', type_='check')
    op.drop_constraint('chk_group_type', 'learning_groups', type_='check')

    op.drop_column('group_memberships', 'teacher_override_reason')
    op.drop_column('group_memberships', 'original_check_mode')
    op.drop_column('group_memberships', 'original_group_type')

    op.drop_column('class_sessions', 'groups_teacher_modified')
    op.drop_column('class_sessions', 'grouping_compressed')
    op.drop_column('class_sessions', 'grouping_warnings')
