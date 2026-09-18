"""grounded_activity_generation

Revision ID: 008_grounded_activity_generation
Revises: 007_curriculum_knowledge_base
Create Date: 2026-09-18 10:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '008_grounded_activity_generation'
down_revision = '007_curriculum_knowledge_base'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('activity_plans',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('prompt_version', sa.String(), nullable=False),
        sa.Column('provider_name', sa.String(), nullable=False),
        sa.Column('model_name', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False, server_default='draft'),
        sa.Column('language', sa.String(), nullable=False, server_default='en'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['session_id'], ['class_sessions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', name='uq_activity_plan_session'),
        sa.CheckConstraint("status = 'draft'", name='chk_activity_plan_status')
    )
    
    op.create_table('group_activities',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('activity_plan_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('group_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('group_name_snapshot', sa.String(), nullable=False),
        sa.Column('group_type_snapshot', sa.String(), nullable=False),
        sa.Column('focus_competency_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('objective', sa.String(), nullable=False),
        sa.Column('duration_minutes', sa.Integer(), nullable=False),
        sa.Column('teacher_attention_minutes', sa.Integer(), nullable=False),
        sa.Column('independent_minutes', sa.Integer(), nullable=False),
        sa.Column('materials', sa.JSON(), nullable=False),
        sa.Column('teacher_actions', sa.JSON(), nullable=False),
        sa.Column('student_actions', sa.JSON(), nullable=False),
        sa.Column('checks_for_understanding', sa.JSON(), nullable=False),
        sa.Column('success_criteria', sa.JSON(), nullable=False),
        sa.Column('adaptations', sa.JSON(), nullable=False),
        sa.Column('generated_by', sa.String(), nullable=False, server_default='llm'),
        sa.Column('approval_status', sa.String(), nullable=False, server_default='pending_teacher_review'),
        sa.Column('prompt_version', sa.String(), nullable=False),
        sa.Column('provider_name', sa.String(), nullable=False),
        sa.Column('model_name', sa.String(), nullable=False),
        sa.Column('prompt_input_hash', sa.String(), nullable=False),
        sa.Column('structured_output_hash', sa.String(), nullable=False),
        sa.Column('generation_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("approval_status = 'pending_teacher_review'", name='chk_grp_act_approval'),
        sa.CheckConstraint('duration_minutes > 0', name='chk_grp_act_duration'),
        sa.CheckConstraint("generated_by = 'llm'", name='chk_grp_act_generated_by'),
        sa.CheckConstraint('independent_minutes >= 0', name='chk_grp_act_indep_min'),
        sa.CheckConstraint('teacher_attention_minutes >= 0', name='chk_grp_act_teacher_min'),
        sa.CheckConstraint('generation_order >= 0', name='chk_grp_act_generation_order'),
        sa.ForeignKeyConstraint(['activity_plan_id'], ['activity_plans.id'], ),
        sa.ForeignKeyConstraint(['focus_competency_id'], ['competencies.id'], ),
        sa.ForeignKeyConstraint(['group_id'], ['learning_groups.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['class_sessions.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('activity_plan_id', 'group_id', name='uq_grp_act_plan_group'),
        sa.UniqueConstraint('activity_plan_id', 'generation_order', name='uq_grp_act_plan_order')
    )
    
    op.create_table('activity_source_citations',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('group_activity_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('curriculum_chunk_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('citation_order', sa.Integer(), nullable=False),
        sa.Column('document_id_snapshot', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('document_title_snapshot', sa.String(), nullable=False),
        sa.Column('source_name_snapshot', sa.String(), nullable=False),
        sa.Column('source_type_snapshot', sa.String(), nullable=False),
        sa.Column('version_snapshot', sa.String(), nullable=False),
        sa.Column('section_title_snapshot', sa.String(), nullable=True),
        sa.Column('page_start_snapshot', sa.Integer(), nullable=True),
        sa.Column('page_end_snapshot', sa.Integer(), nullable=True),
        sa.Column('chunk_index_snapshot', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint('citation_order >= 0', name='chk_act_cit_order'),
        sa.ForeignKeyConstraint(['curriculum_chunk_id'], ['curriculum_chunks.id'], ),
        sa.ForeignKeyConstraint(['group_activity_id'], ['group_activities.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('group_activity_id', 'curriculum_chunk_id', name='uq_act_cit_activity_chunk')
    )

def downgrade():
    op.drop_table('activity_source_citations')
    op.drop_table('group_activities')
    op.drop_table('activity_plans')
