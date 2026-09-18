"""rotation scheduler

Revision ID: 006_rotation_scheduler
Revises: 005_priority_hardening
Create Date: 2026-09-17 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '006_rotation_scheduler'
down_revision = '005_priority_hardening'
branch_labels = None
depends_on = None

def upgrade() -> None:
    rotationslottype = postgresql.ENUM('whole_class_opening', 'group_visit', 'transition', 'whole_class_closing', name='rotationslottype')
    rotationslottype.create(op.get_bind(), checkfirst=True)

    op.create_table('rotation_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_duration_minutes', sa.Integer(), nullable=False),
        sa.Column('opening_minutes', sa.Integer(), nullable=False),
        sa.Column('closing_minutes', sa.Integer(), nullable=False),
        sa.Column('transition_minutes_each', sa.Integer(), nullable=False),
        sa.Column('transition_total_minutes', sa.Integer(), nullable=False),
        sa.Column('teacher_attention_budget_minutes', sa.Integer(), nullable=False),
        sa.Column('minimum_group_attention_minutes', sa.Integer(), nullable=False),
        sa.Column('group_count', sa.Integer(), nullable=False),
        sa.Column('algorithm_version', sa.String(), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('session_duration_minutes > 0', name='chk_rp_session_duration'),
        sa.CheckConstraint('opening_minutes >= 0', name='chk_rp_opening_minutes'),
        sa.CheckConstraint('closing_minutes >= 0', name='chk_rp_closing_minutes'),
        sa.CheckConstraint('transition_minutes_each >= 0', name='chk_rp_trans_min_each'),
        sa.CheckConstraint('transition_total_minutes >= 0', name='chk_rp_trans_total'),
        sa.CheckConstraint('teacher_attention_budget_minutes > 0', name='chk_rp_budget'),
        sa.CheckConstraint('minimum_group_attention_minutes > 0', name='chk_rp_min_group_attention'),
        sa.CheckConstraint('group_count > 0', name='chk_rp_group_count'),
        sa.ForeignKeyConstraint(['session_id'], ['class_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', name='uq_rotation_plan_session_id')
    )

    op.create_table('rotation_slots',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('rotation_plan_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('sequence_index', sa.Integer(), nullable=False),
        sa.Column('slot_type', postgresql.ENUM('whole_class_opening', 'group_visit', 'transition', 'whole_class_closing', name='rotationslottype', create_type=False), nullable=False),
        sa.Column('group_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('start_minute', sa.Integer(), nullable=False),
        sa.Column('end_minute', sa.Integer(), nullable=False),
        sa.Column('duration_minutes', sa.Integer(), nullable=False),
        sa.Column('group_name_snapshot', sa.String(), nullable=True),
        sa.Column('group_type_snapshot', sa.String(), nullable=True),
        sa.Column('priority_score_snapshot', sa.Float(), nullable=True),
        sa.Column('algorithm_priority_rank_snapshot', sa.Integer(), nullable=True),
        sa.Column('teacher_rank_snapshot', sa.Integer(), nullable=True),
        sa.Column('effective_rank_snapshot', sa.Integer(), nullable=True),
        sa.Column('student_count_snapshot', sa.Integer(), nullable=True),
        sa.Column('base_minutes', sa.Integer(), nullable=True),
        sa.Column('weighted_extra_minutes', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('sequence_index >= 0', name='chk_rs_seq_index'),
        sa.CheckConstraint('start_minute >= 0', name='chk_rs_start_minute'),
        sa.CheckConstraint('end_minute > start_minute', name='chk_rs_end_gt_start'),
        sa.CheckConstraint('duration_minutes > 0', name='chk_rs_duration_gt_zero'),
        sa.CheckConstraint('duration_minutes = end_minute - start_minute', name='chk_rs_duration_calc'),
        sa.CheckConstraint("(slot_type = 'group_visit' AND group_id IS NOT NULL) OR (slot_type != 'group_visit' AND group_id IS NULL)", name='chk_rs_group_id_semantics'),
        sa.CheckConstraint(
            "(slot_type != 'group_visit') OR ("
            "group_id IS NOT NULL AND "
            "group_name_snapshot IS NOT NULL AND "
            "group_type_snapshot IS NOT NULL AND "
            "priority_score_snapshot IS NOT NULL AND "
            "priority_score_snapshot >= 0 AND "
            "priority_score_snapshot <= 100 AND "
            "algorithm_priority_rank_snapshot IS NOT NULL AND "
            "algorithm_priority_rank_snapshot > 0 AND "
            "effective_rank_snapshot IS NOT NULL AND "
            "effective_rank_snapshot > 0 AND "
            "student_count_snapshot IS NOT NULL AND "
            "student_count_snapshot > 0 AND "
            "base_minutes IS NOT NULL AND "
            "base_minutes > 0 AND "
            "weighted_extra_minutes IS NOT NULL AND "
            "weighted_extra_minutes >= 0 AND "
            "reason IS NOT NULL"
            ")",
            name='chk_rs_group_visit_snapshot'
        ),
        sa.ForeignKeyConstraint(['group_id'], ['learning_groups.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['rotation_plan_id'], ['rotation_plans.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['session_id'], ['class_sessions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('rotation_plan_id', 'sequence_index', name='uq_rotation_slot_seq')
    )

def downgrade() -> None:
    op.drop_table('rotation_slots')
    op.drop_table('rotation_plans')
    op.execute("DROP TYPE IF EXISTS rotationslottype")
