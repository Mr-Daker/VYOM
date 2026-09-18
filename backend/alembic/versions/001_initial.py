"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2026-09-17 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ENUM

revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    userrole = ENUM('teacher', 'admin', name='userrole', create_type=False)
    userrole.create(op.get_bind(), checkfirst=True)
    op.create_table('users',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('role', userrole, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email')
    )

    op.create_table('competencies',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('code', sa.String(), nullable=False),
        sa.Column('subject', sa.String(), nullable=False),
        sa.Column('grade', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
        sa.CheckConstraint('grade IN (1, 2, 3)', name='check_comp_grade')
    )

    op.create_table('classrooms',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('teacher_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('school_name', sa.String(), nullable=True),
        sa.Column('default_language', sa.String(), nullable=True),
        sa.Column('secondary_language', sa.String(), nullable=True),
        sa.Column('default_duration_minutes', sa.Integer(), nullable=True),
        sa.Column('max_groups', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['teacher_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('default_duration_minutes > 0', name='check_duration_positive'),
        sa.CheckConstraint('max_groups > 0', name='check_groups_positive')
    )

    op.create_table('competency_prerequisites',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('competency_id', UUID(as_uuid=True), nullable=False),
        sa.Column('prerequisite_competency_id', UUID(as_uuid=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['competency_id'], ['competencies.id'], ),
        sa.ForeignKeyConstraint(['prerequisite_competency_id'], ['competencies.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('competency_id', 'prerequisite_competency_id', name='uq_competency_prerequisite'),
        sa.CheckConstraint('competency_id != prerequisite_competency_id', name='check_no_self_prerequisite')
    )

    op.create_table('students',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('classroom_id', UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('grade', sa.Integer(), nullable=False),
        sa.Column('preferred_language', sa.String(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['classroom_id'], ['classrooms.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('grade IN (1, 2, 3)', name='check_valid_grade')
    )

    masterystate = ENUM('unknown', 'needs_support', 'developing', 'mastered', name='masterystate', create_type=False)
    masterystate.create(op.get_bind(), checkfirst=True)
    op.create_table('student_mastery',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', UUID(as_uuid=True), nullable=False),
        sa.Column('competency_id', UUID(as_uuid=True), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('state', masterystate, nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('last_updated', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['competency_id'], ['competencies.id'], ),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id', 'competency_id', name='uq_student_competency_mastery'),
        sa.CheckConstraint('score >= 0 AND score <= 1', name='check_mastery_score_bounds'),
        sa.CheckConstraint('confidence IS NULL OR (confidence >= 0 AND confidence <= 1)', name='check_mastery_confidence_bounds')
    )

    sessionstatus = ENUM('draft', 'attendance_recorded', 'grouped', 'scheduled', 'activities_ready', 'teacher_approved', 'in_progress', 'completed', name='sessionstatus', create_type=False)
    sessionstatus.create(op.get_bind(), checkfirst=True)
    op.create_table('class_sessions',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('classroom_id', UUID(as_uuid=True), nullable=False),
        sa.Column('date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('subject', sa.String(), nullable=True),
        sa.Column('target_competency_id', UUID(as_uuid=True), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=True),
        sa.Column('available_materials', sa.JSON(), nullable=True),
        sa.Column('status', sessionstatus, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['classroom_id'], ['classrooms.id'], ),
        sa.ForeignKeyConstraint(['target_competency_id'], ['competencies.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('duration_minutes > 0', name='check_session_duration')
    )

    evidencesource = ENUM('initial_assessment', 'exit_ticket', 'teacher_observation', 'manual_assessment', name='evidencesource', create_type=False)
    evidencesource.create(op.get_bind(), checkfirst=True)
    op.create_table('mastery_evidence',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', UUID(as_uuid=True), nullable=False),
        sa.Column('competency_id', UUID(as_uuid=True), nullable=False),
        sa.Column('session_id', UUID(as_uuid=True), nullable=True),
        sa.Column('source_type', evidencesource, nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['competency_id'], ['competencies.id'], ),
        sa.ForeignKeyConstraint(['session_id'], ['class_sessions.id'], ),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.CheckConstraint('score >= 0 AND score <= 1', name='check_evidence_score_bounds'),
        sa.CheckConstraint('confidence IS NULL OR (confidence >= 0 AND confidence <= 1)', name='check_evidence_confidence_bounds')
    )

    attendancestatus = ENUM('present', 'absent', 'late', name='attendancestatus', create_type=False)
    attendancestatus.create(op.get_bind(), checkfirst=True)
    op.create_table('attendance_records',
        sa.Column('id', UUID(as_uuid=True), nullable=False),
        sa.Column('student_id', UUID(as_uuid=True), nullable=False),
        sa.Column('class_session_id', UUID(as_uuid=True), nullable=False),
        sa.Column('status', attendancestatus, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['class_session_id'], ['class_sessions.id'], ),
        sa.ForeignKeyConstraint(['student_id'], ['students.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('student_id', 'class_session_id', name='uq_student_session_attendance')
    )


def downgrade() -> None:
    op.drop_table('attendance_records')
    op.drop_table('mastery_evidence')
    op.drop_table('class_sessions')
    op.drop_table('student_mastery')
    op.drop_table('students')
    op.drop_table('competency_prerequisites')
    op.drop_table('classrooms')
    op.drop_table('competencies')
    op.drop_table('users')
    
    op.execute('DROP TYPE attendancestatus')
    op.execute('DROP TYPE evidencesource')
    op.execute('DROP TYPE sessionstatus')
    op.execute('DROP TYPE masterystate')
    op.execute('DROP TYPE userrole')
